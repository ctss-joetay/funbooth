"""Live booth state shared by the operator and display iPads over WebSockets.

Devices: the operator (iPad or laptop) runs the booth, the display iPad faces the guests,
and the photo is shot by whichever device is chosen as the camera: the operator device, the
display itself, or a separate phone running the camera page.

Flow: guests pick a theme and tap "Take my photo" (or the operator / camera taps the
shutter) -> server broadcasts a countdown -> the camera device uploads the frame -> the AI
restyles it -> everyone gets the result. Only the operator can print or send photos.
While guests pose, the camera device streams small JPEG preview frames that the server
relays to the display.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

from fastapi import WebSocket

from .ai import AIError, ImageAI
from .config import STATIC_DIR, Settings
from .printing import LAYOUTS, layout_for
from .storage import PhotoRecord, PhotoStore, normalize_jpeg
from .themes import CUSTOM_THEME, THEMES, build_prompt, build_video_prompt, get_theme
from .video import VideoAI

log = logging.getLogger("funbooth.booth")

ROLES = {"operator", "display", "camera"}
CAMERA_LABELS = {"operator": "operator", "display": "guest iPad", "camera": "phone"}
THEME_IDS = {t.id for t in THEMES} | {CUSTOM_THEME.id}
GUEST_THEME_IDS = [t.id for t in THEMES]  # Custom needs a typed prompt, so it's operator-only
CAPTURE_GRACE_SECONDS = 20  # how long after the countdown we wait for the photo upload
MAX_PARALLEL_AI = 3
MAX_PARALLEL_VIDEO = 2
SAMPLE_SIZE = 1024
MAX_PREVIEW_FRAME = 400_000


@dataclass
class Prefs:
    """Operator-editable settings, persisted to DATA_DIR/prefs.json."""

    event_name: str = "Fun Booth"
    theme_id: str = THEMES[0].id
    custom_prompt: str = ""
    camera_source: str = "operator"  # which device shoots: operator | display | camera (phone)
    countdown: int = 3
    orientation: str = "landscape"  # print layout: landscape (6x4) | portrait (4x6)
    print_qr: bool = True  # QR code on the printed photo
    auto_video: bool = False  # make a video clip of every finished photo (costs per clip)
    guest_themes: list[str] = field(default_factory=lambda: list(GUEST_THEME_IDS))

    def update(self, data: dict) -> None:
        if "event_name" in data:
            self.event_name = str(data["event_name"]).strip()[:80]
        if data.get("theme_id") in THEME_IDS:
            self.theme_id = data["theme_id"]
        if "custom_prompt" in data:
            self.custom_prompt = str(data["custom_prompt"])[:600]
        if data.get("camera_source") in CAMERA_LABELS:
            self.camera_source = data["camera_source"]
        if "countdown" in data:
            try:
                self.countdown = max(0, min(10, int(data["countdown"])))
            except (TypeError, ValueError):
                pass
        if data.get("orientation") in LAYOUTS:
            self.orientation = data["orientation"]
        for key in ("print_qr", "auto_video"):
            if key in data:
                setattr(self, key, bool(data[key]))
        if isinstance(data.get("guest_themes"), list):
            chosen = [t for t in GUEST_THEME_IDS if t in data["guest_themes"]]
            if chosen:  # guests always need at least one theme
                self.guest_themes = chosen


@dataclass
class Client:
    id: str
    role: str
    ws: WebSocket
    camera_ready: bool = False
    wants_preview: bool = False
    connected_at: float = field(default_factory=time.monotonic)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Booth:
    def __init__(self, settings: Settings, ai: ImageAI, video_ai: VideoAI):
        self.settings = settings
        self.ai = ai
        self.video_ai = video_ai
        self.store = PhotoStore(settings.data_dir)
        self._prefs_path = settings.data_dir / "prefs.json"
        self.prefs = self._load_prefs()
        self.samples_dir = settings.data_dir / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.samples = {t.id: self._sample_url(t.id) for t in THEMES}

        self.phase = "idle"  # idle | countdown | processing | result | error
        self.message = ""
        self.current: PhotoRecord | None = None
        self.qr_photo: PhotoRecord | None = None  # QR the operator sent to the guest screen
        self.clients: dict[str, Client] = {}

        self._countdown_seq = 0
        self._ai_slots = asyncio.Semaphore(MAX_PARALLEL_AI)
        self._video_slots = asyncio.Semaphore(MAX_PARALLEL_VIDEO)
        self._tasks: set[asyncio.Task] = set()
        self._making_samples = False

    # -- prefs ----------------------------------------------------------------------------

    def _load_prefs(self) -> Prefs:
        prefs = Prefs(event_name=self.settings.default_event_name)
        try:
            prefs.update(json.loads(self._prefs_path.read_text()))
        except (OSError, ValueError):
            pass
        return prefs

    def _save_prefs(self) -> None:
        self._prefs_path.write_text(json.dumps(asdict(self.prefs)))

    # -- theme samples --------------------------------------------------------------------

    def sample_path(self, theme_id: str):
        return self.samples_dir / f"{theme_id}.jpg"

    def _sample_url(self, theme_id: str) -> str | None:
        """Operator-made samples win; otherwise fall back to images shipped in static/samples."""
        made = self.sample_path(theme_id)
        if made.exists():
            return f"/samples/{theme_id}.jpg?v={int(made.stat().st_mtime)}"
        if (STATIC_DIR / "samples" / f"{theme_id}.jpg").exists():
            return f"/static/samples/{theme_id}.jpg"
        return None

    def _save_sample(self, theme_id: str, image: bytes) -> None:
        self.sample_path(theme_id).write_bytes(normalize_jpeg(image, SAMPLE_SIZE, 88))
        self.samples[theme_id] = self._sample_url(theme_id)

    # -- connections ----------------------------------------------------------------------

    def active_camera(self) -> Client | None:
        """The most recently connected ready camera of the chosen kind."""
        ready = [c for c in self.clients.values() if c.role == self.prefs.camera_source and c.camera_ready]
        return max(ready, key=lambda c: c.connected_at) if ready else None

    def snapshot(self) -> dict:
        camera = self.active_camera()
        return {
            "type": "state",
            "phase": self.phase,
            "message": self.message,
            "prefs": asdict(self.prefs),
            "photo": self.current.public() if self.current else None,
            "qr": self.qr_photo.public() if self.qr_photo else None,
            "samples": self.samples,
            "making_samples": self._making_samples,
            "camera_id": camera.id if camera else None,
            "preview_wanted": any(c.wants_preview and c is not camera for c in self.clients.values()),
            "devices": {role: sum(c.role == role for c in self.clients.values()) for role in ROLES},
            "ai_mode": self.ai.mode_label,
        }

    async def connect(self, ws: WebSocket, role: str) -> str:
        client = Client(id=uuid.uuid4().hex[:12], role=role, ws=ws)
        self.clients[client.id] = client
        await self._send(client, {"type": "welcome", "client_id": client.id, "role": role})
        await self.broadcast_state()
        return client.id

    async def disconnect(self, client_id: str) -> None:
        if self.clients.pop(client_id, None):
            await self.broadcast_state()

    async def _send(self, client: Client, message: dict) -> bool:
        try:
            async with client.send_lock:
                await client.ws.send_json(message)
            return True
        except Exception:  # socket already gone; the receive loop will clean it up
            return False

    async def relay_frame(self, client_id: str, frame: bytes) -> None:
        """Forward a live preview frame from the active camera to the screens that want it.

        A viewer that is still receiving the previous frame skips this one, so a slow
        connection never builds up a backlog.
        """
        camera = self.active_camera()
        if not camera or camera.id != client_id or len(frame) > MAX_PREVIEW_FRAME:
            return

        async def push(viewer: Client) -> None:
            try:
                async with viewer.send_lock:
                    await viewer.ws.send_bytes(frame)
            except Exception:
                pass

        viewers = [c for c in self.clients.values() if c.wants_preview and c is not camera]
        await asyncio.gather(*(push(v) for v in viewers if not v.send_lock.locked()))

    async def broadcast(self, message: dict, role: str | None = None) -> None:
        targets = [c for c in list(self.clients.values()) if role is None or c.role == role]
        await asyncio.gather(*(self._send(c, message) for c in targets))

    async def broadcast_state(self) -> None:
        await self.broadcast(self.snapshot())

    async def toast(self, client_id: str, text: str, level: str = "error") -> None:
        client = self.clients.get(client_id)
        if client:
            await self._send(client, {"type": "toast", "level": level, "text": text})

    async def notify_operators(self, text: str, level: str = "info") -> None:
        await self.broadcast({"type": "toast", "level": level, "text": text}, role="operator")

    # -- messages from devices ------------------------------------------------------------

    async def handle(self, client_id: str, msg: dict) -> None:
        client = self.clients.get(client_id)
        if not client or not isinstance(msg, dict):
            return
        kind = msg.get("type")

        if kind == "camera":
            client.camera_ready = bool(msg.get("ready"))
            await self.broadcast_state()
        elif kind == "preview":
            client.wants_preview = bool(msg.get("want"))
            await self.broadcast_state()
        elif client.role == "operator" or self._host_pin_ok(msg.get("pin")):
            # The guest iPad unlocks host controls with the PIN (one-iPad setups).
            await self._handle_operator(client, kind, msg)
        elif client.role == "display":
            await self._handle_guest(client, kind, msg)
        elif kind == "start" and self.phase in ("idle", "result", "error"):  # camera's shutter
            await self.start_countdown(client)

    def _host_pin_ok(self, pin) -> bool:
        return isinstance(pin, str) and hmac.compare_digest(pin.encode(), self.settings.booth_pin.encode())

    async def _handle_guest(self, client: Client, kind: str, msg: dict) -> None:
        """Guests can pick a theme and run the camera, but never print or send photos."""
        if kind == "theme":
            theme_id = msg.get("theme_id")
            if theme_id in self.prefs.guest_themes and theme_id != self.prefs.theme_id:
                self.prefs.theme_id = theme_id
                self._save_prefs()
                await self.broadcast_state()
        elif kind == "start" and self.phase in ("idle", "result", "error"):
            await self.start_countdown(client)
        elif kind == "reset" and self.phase in ("result", "error"):
            await self.reset()

    async def _handle_operator(self, client: Client, kind: str, msg: dict) -> None:
        photo_id = str(msg.get("photo_id") or "")
        if kind == "prefs":
            self.prefs.update(msg.get("prefs") or {})
            self._save_prefs()
            await self.broadcast_state()
        elif kind == "start":
            await self.start_countdown(client)
        elif kind == "reset":
            await self.reset()
        elif kind == "regenerate":
            await self.regenerate(photo_id, client.id)
        elif kind == "send_qr":
            await self.send_qr(photo_id or None, client.id)
        elif kind == "set_sample":
            await self.set_sample(photo_id, client.id)
        elif kind == "make_samples":
            await self.make_samples(photo_id, client.id)
        elif kind == "make_video":
            await self.make_video(photo_id, client.id)

    # -- booth actions --------------------------------------------------------------------

    async def start_countdown(self, requested_by: Client) -> None:
        if self.phase == "countdown":
            return
        capturer = self.active_camera()
        if not capturer:
            where = CAMERA_LABELS[self.prefs.camera_source]
            await self.toast(requested_by.id, f"The {where} camera isn't ready yet.")
            return

        self._countdown_seq += 1
        seq = self._countdown_seq
        self.phase, self.message, self.current, self.qr_photo = "countdown", "", None, None
        await self.broadcast_state()
        await self.broadcast(
            {"type": "countdown", "seconds": self.prefs.countdown, "capturer": capturer.id, "seq": seq}
        )
        self._spawn(self._capture_watchdog(seq, self.prefs.countdown + CAPTURE_GRACE_SECONDS))

    async def _capture_watchdog(self, seq: int, timeout: float) -> None:
        await asyncio.sleep(timeout)
        if self.phase == "countdown" and self._countdown_seq == seq:
            self.phase, self.message = "error", "No photo arrived from the camera. Please try again."
            await self.broadcast_state()

    async def ingest(self, image_bytes: bytes) -> PhotoRecord:
        """A device uploaded a photo (camera capture or file). Raises ValueError if unreadable."""
        jpeg = await asyncio.to_thread(normalize_jpeg, image_bytes)
        p = self.prefs
        rec = await asyncio.to_thread(self.store.create, jpeg, p.theme_id, p.custom_prompt, p.orientation)
        self.current, self.qr_photo = rec, None
        self.phase, self.message = "processing", ""
        await self.broadcast_state()
        await self.broadcast({"type": "photo", "photo": rec.public()})
        self._spawn(self._generate(rec))
        return rec

    async def regenerate(self, photo_id: str, client_id: str | None = None) -> None:
        rec = self.store.get(photo_id)
        if not rec:
            if client_id:
                await self.toast(client_id, "That photo no longer exists.")
            return
        if rec.status == "processing":
            return
        rec.theme_id, rec.custom_prompt = self.prefs.theme_id, self.prefs.custom_prompt
        rec.status, rec.error = "processing", ""
        rec.clear_video()  # the old clip shows the old theme
        self.store.save(rec)
        self.current, self.qr_photo = rec, None
        self.phase, self.message = "processing", ""
        await self.broadcast_state()
        await self.broadcast({"type": "photo", "photo": rec.public()})
        self._spawn(self._generate(rec))

    async def reset(self) -> None:
        self._countdown_seq += 1  # cancels any pending capture watchdog
        self.phase, self.message, self.current, self.qr_photo = "idle", "", None, None
        await self.broadcast_state()

    async def send_qr(self, photo_id: str | None, client_id: str) -> None:
        """Show (or hide, with no photo_id) a download QR code on the guest screen."""
        if photo_id is None:
            self.qr_photo = None
        else:
            rec = self.store.get(photo_id)
            if not rec or rec.status != "done":
                await self.toast(client_id, "That photo isn't ready to send yet.")
                return
            self.qr_photo = rec
        await self.broadcast_state()

    async def set_sample(self, photo_id: str, client_id: str) -> None:
        rec = self.store.get(photo_id)
        if not rec or rec.status != "done" or rec.theme_id == CUSTOM_THEME.id:
            await self.toast(client_id, "Pick a finished photo from one of the themes first.")
            return
        result = self.store.path(rec.id, "result").read_bytes()
        await asyncio.to_thread(self._save_sample, rec.theme_id, result)
        await self.broadcast_state()
        await self.toast(client_id, f"Saved as the sample for {get_theme(rec.theme_id).name}.", "info")

    async def make_samples(self, photo_id: str, client_id: str) -> None:
        """Restyle one photo in every theme to build the guest carousel's sample pictures."""
        rec = self.store.get(photo_id)
        if not rec:
            await self.toast(client_id, "Pick a photo first.")
            return
        if self._making_samples:
            await self.toast(client_id, "Samples are already being made.", "info")
            return
        self._making_samples = True
        await self.broadcast_state()
        await self.notify_operators(f"Making samples for {len(THEMES)} themes. This takes a minute or two…")
        self._spawn(self._make_samples(rec))

    async def _make_samples(self, rec: PhotoRecord) -> None:
        original = self.store.path(rec.id, "original").read_bytes()
        ratio = layout_for(rec.orientation)["ai_ratio"]
        failures: list[str] = []

        async def one(theme) -> None:
            try:
                async with self._ai_slots:
                    raw = await self.ai.transform(original, build_prompt(theme), ratio)
                await asyncio.to_thread(self._save_sample, theme.id, raw)
                await self.broadcast_state()
            except (AIError, ValueError) as exc:
                log.warning("sample for %s failed: %s", theme.id, exc)
                failures.append(theme.name)

        try:
            await asyncio.gather(*(one(t) for t in THEMES))
        finally:
            self._making_samples = False
            await self.broadcast_state()
        if failures:
            await self.notify_operators(f"Samples done, but these failed: {', '.join(failures)}.", "error")
        else:
            await self.notify_operators("All theme samples are ready.")

    async def _generate(self, rec: PhotoRecord) -> None:
        theme = get_theme(rec.theme_id)
        prompt = build_prompt(theme, rec.custom_prompt)
        ratio = layout_for(rec.orientation)["ai_ratio"]
        started = time.monotonic()
        try:
            original = self.store.path(rec.id, "original").read_bytes()
            async with self._ai_slots:
                raw = await self.ai.transform(original, prompt, ratio)
            result = await asyncio.to_thread(normalize_jpeg, raw, 4096, 93)
            self.store.path(rec.id, "result").write_bytes(result)
            rec.status, rec.error = "done", ""
            rec.version += 1
            log.info("photo %s done in %.1fs (%s)", rec.id, time.monotonic() - started, theme.id)
        except AIError as exc:
            rec.status, rec.error = "error", str(exc)
        except ValueError:
            rec.status, rec.error = "error", "The AI sent back an image we couldn't read."
        except Exception:
            log.exception("generation failed for %s", rec.id)
            rec.status, rec.error = "error", "Something went wrong while creating the photo."
        if rec.status == "error":
            log.warning("photo %s failed: %s", rec.id, rec.error)

        self.store.save(rec)
        if self.current and self.current.id == rec.id:
            self.current = rec
            self.phase = "result" if rec.status == "done" else "error"
            self.message = rec.error
            await self.broadcast_state()
        await self.broadcast({"type": "photo", "photo": rec.public()})
        if rec.status == "done" and self.prefs.auto_video:
            await self.make_video(rec.id)

    # -- video clips ----------------------------------------------------------------------

    async def make_video(self, photo_id: str, client_id: str | None = None) -> None:
        """Animate a finished photo into a short clip (a few minutes at most, runs in the background)."""
        rec = self.store.get(photo_id)
        if not rec or rec.status != "done":
            if client_id:
                await self.toast(client_id, "Pick a finished photo first.")
            return
        if rec.video_status == "processing":
            return
        rec.clear_video()
        rec.video_status = "processing"
        self.store.save(rec)
        await self._photo_changed(rec)
        self._spawn(self._make_video(rec.id))

    async def _make_video(self, photo_id: str) -> None:
        rec = self.store.get(photo_id)
        theme = get_theme(rec.theme_id)
        ratio = layout_for(rec.orientation)["ai_ratio"]
        try:
            still = self.store.path(rec.id, "result").read_bytes()
            async with self._video_slots:
                clip = await self.video_ai.animate(still, build_video_prompt(theme), ratio)
            self.store.file(rec.id, "clip.mp4").write_bytes(clip.data)
            error, model, cost = "", clip.model, clip.cost
        except AIError as exc:
            error, model, cost = str(exc), "", None
        except Exception:
            log.exception("video failed for %s", photo_id)
            error, model, cost = "Something went wrong while making the video.", "", None

        rec = self.store.get(photo_id) or rec  # reload: the photo may have changed meanwhile
        if rec.video_status != "processing":
            return  # restyled while we were busy; this clip is stale
        rec.video_status = "error" if error else "done"
        rec.video_error, rec.video_model, rec.video_cost = error, model, cost
        if not error:
            rec.video_version += 1
        self.store.save(rec)
        if error:
            log.warning("video for %s failed: %s", photo_id, error)
            await self.notify_operators(f"Video failed: {error}", "error")
        await self._photo_changed(rec)

    async def _photo_changed(self, rec: PhotoRecord) -> None:
        if self.current and self.current.id == rec.id:
            self.current = rec
            await self.broadcast_state()
        await self.broadcast({"type": "photo", "photo": rec.public()})

    async def recover(self) -> None:
        """After a restart, nothing is still working on 'processing' photos or clips."""
        for rec in await asyncio.to_thread(self.store.recent, 500):
            changed = False
            if rec.status == "processing":
                rec.status, rec.error, changed = "error", "Interrupted by a server restart. Tap Restyle.", True
            if rec.video_status == "processing":
                rec.video_status, rec.video_error, changed = "error", "Interrupted by a server restart.", True
            if changed:
                self.store.save(rec)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self.ai.aclose()
        await self.video_ai.aclose()
