"""Live booth state shared by the operator and display iPads over WebSockets.

Flow: operator taps "Take photo" -> server picks the device whose camera will shoot and
broadcasts a countdown -> that device uploads the frame -> the AI restyles it -> everyone
gets the result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

from fastapi import WebSocket

from .ai import AIError, ImageAI
from .config import Settings
from .printing import LAYOUTS, layout_for
from .storage import PhotoRecord, PhotoStore, normalize_jpeg
from .themes import CUSTOM_THEME, THEMES, build_prompt, get_theme

log = logging.getLogger("funbooth.booth")

ROLES = {"operator", "display"}
THEME_IDS = {t.id for t in THEMES} | {CUSTOM_THEME.id}
CAPTURE_GRACE_SECONDS = 20  # how long after the countdown we wait for the photo upload
MAX_PARALLEL_AI = 3


@dataclass
class Prefs:
    """Operator-editable settings, persisted to DATA_DIR/prefs.json."""

    event_name: str = "Fun Booth"
    theme_id: str = THEMES[0].id
    custom_prompt: str = ""
    camera_source: str = "display"  # which iPad's camera shoots: display | operator
    countdown: int = 3
    orientation: str = "landscape"  # print layout: landscape (6x4) | portrait (4x6)
    print_qr: bool = True  # QR code on the printed photo
    show_qr: bool = True  # QR code on the display next to the result

    def update(self, data: dict) -> None:
        if "event_name" in data:
            self.event_name = str(data["event_name"]).strip()[:80]
        if data.get("theme_id") in THEME_IDS:
            self.theme_id = data["theme_id"]
        if "custom_prompt" in data:
            self.custom_prompt = str(data["custom_prompt"])[:600]
        if data.get("camera_source") in ("display", "operator"):
            self.camera_source = data["camera_source"]
        if "countdown" in data:
            try:
                self.countdown = max(0, min(10, int(data["countdown"])))
            except (TypeError, ValueError):
                pass
        if data.get("orientation") in LAYOUTS:
            self.orientation = data["orientation"]
        for key in ("print_qr", "show_qr"):
            if key in data:
                setattr(self, key, bool(data[key]))


@dataclass
class Client:
    id: str
    role: str
    ws: WebSocket
    camera_ready: bool = False
    connected_at: float = field(default_factory=time.monotonic)


class Booth:
    def __init__(self, settings: Settings, ai: ImageAI):
        self.settings = settings
        self.ai = ai
        self.store = PhotoStore(settings.data_dir)
        self._prefs_path = settings.data_dir / "prefs.json"
        self.prefs = self._load_prefs()

        self.phase = "idle"  # idle | countdown | processing | result | error
        self.message = ""
        self.current: PhotoRecord | None = None
        self.clients: dict[str, Client] = {}

        self._countdown_seq = 0
        self._ai_slots = asyncio.Semaphore(MAX_PARALLEL_AI)
        self._tasks: set[asyncio.Task] = set()

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

    # -- connections ----------------------------------------------------------------------

    def snapshot(self) -> dict:
        def any_camera(role: str) -> bool:
            return any(c.camera_ready for c in self.clients.values() if c.role == role)

        return {
            "type": "state",
            "phase": self.phase,
            "message": self.message,
            "prefs": asdict(self.prefs),
            "photo": self.current.public() if self.current else None,
            "devices": {
                "operator": sum(c.role == "operator" for c in self.clients.values()),
                "display": sum(c.role == "display" for c in self.clients.values()),
                "operator_camera": any_camera("operator"),
                "display_camera": any_camera("display"),
            },
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
            await client.ws.send_json(message)
            return True
        except Exception:  # socket already gone; the receive loop will clean it up
            return False

    async def broadcast(self, message: dict) -> None:
        await asyncio.gather(*(self._send(c, message) for c in list(self.clients.values())))

    async def broadcast_state(self) -> None:
        await self.broadcast(self.snapshot())

    async def toast(self, client_id: str, text: str, level: str = "error") -> None:
        client = self.clients.get(client_id)
        if client:
            await self._send(client, {"type": "toast", "level": level, "text": text})

    # -- messages from devices ------------------------------------------------------------

    async def handle(self, client_id: str, msg: dict) -> None:
        client = self.clients.get(client_id)
        if not client or not isinstance(msg, dict):
            return
        kind = msg.get("type")

        if kind == "camera":
            client.camera_ready = bool(msg.get("ready"))
            await self.broadcast_state()
            return
        if client.role != "operator":
            return  # the display only reports its camera

        if kind == "prefs":
            self.prefs.update(msg.get("prefs") or {})
            self._save_prefs()
            await self.broadcast_state()
        elif kind == "start":
            await self.start_countdown(client)
        elif kind == "reset":
            await self.reset()
        elif kind == "regenerate":
            await self.regenerate(str(msg.get("photo_id", "")), client_id)
        elif kind == "show":
            await self.show(str(msg.get("photo_id", "")), client_id)

    # -- booth actions --------------------------------------------------------------------

    def _pick_capturer(self, requested_by: Client) -> Client | None:
        if self.prefs.camera_source == "operator":
            if requested_by.camera_ready:
                return requested_by
            role = "operator"
        else:
            role = "display"
        ready = [c for c in self.clients.values() if c.role == role and c.camera_ready]
        return max(ready, key=lambda c: c.connected_at) if ready else None

    async def start_countdown(self, requested_by: Client) -> None:
        if self.phase == "countdown":
            return
        capturer = self._pick_capturer(requested_by)
        if not capturer:
            where = "this iPad" if self.prefs.camera_source == "operator" else "the display iPad"
            await self.toast(requested_by.id, f"The camera on {where} isn't ready yet.")
            return

        self._countdown_seq += 1
        seq = self._countdown_seq
        self.phase, self.message, self.current = "countdown", "", None
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
        self.current = rec
        self.phase, self.message = "processing", ""
        await self.broadcast_state()
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
        self.store.save(rec)
        self.current = rec
        self.phase, self.message = "processing", ""
        await self.broadcast_state()
        await self.broadcast({"type": "photo", "photo": rec.public()})
        self._spawn(self._generate(rec))

    async def show(self, photo_id: str, client_id: str | None = None) -> None:
        rec = self.store.get(photo_id)
        if not rec:
            if client_id:
                await self.toast(client_id, "That photo no longer exists.")
            return
        self.current = rec
        self.phase = {"done": "result", "error": "error"}.get(rec.status, "processing")
        self.message = rec.error
        await self.broadcast_state()

    async def reset(self) -> None:
        self._countdown_seq += 1  # cancels any pending capture watchdog
        self.phase, self.message, self.current = "idle", "", None
        await self.broadcast_state()

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

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self.ai.aclose()
