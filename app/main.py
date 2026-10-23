"""Fun Booth web server.

Run locally:  uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import asyncio
import hmac
import html
import io
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import segno
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .ai import AIError, ImageAI
from .booth import ROLES, Booth
from .config import STATIC_DIR, Settings, load_settings
from .printing import compose_print
from .storage import normalize_jpeg, valid_id
from .themes import all_themes, get_theme

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("funbooth")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
THUMB_SIZE = 360


def _timezone() -> ZoneInfo:
    try:
        return ZoneInfo(os.getenv("TIMEZONE", "UTC"))
    except ZoneInfoNotFoundError:
        log.warning("Unknown TIMEZONE %r, using UTC", os.getenv("TIMEZONE"))
        return ZoneInfo("UTC")


def create_app(settings: Settings | None = None, ai: ImageAI | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    booth = Booth(settings, ai or ImageAI(settings))
    tz = _timezone()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log.info("Fun Booth ready. AI: %s. Data: %s", booth.ai.mode_label, settings.data_dir)
        yield
        await booth.shutdown()

    app = FastAPI(title="Fun Booth", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.booth = booth
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def pin_ok(pin: str) -> bool:
        return hmac.compare_digest(pin.encode(), settings.booth_pin.encode())

    def require_pin(x_booth_pin: str = Header(default="")) -> None:
        if not pin_ok(x_booth_pin):
            raise HTTPException(status_code=401, detail="Wrong PIN")

    def base_url(request: Request) -> str:
        return settings.public_url or str(request.base_url).rstrip("/")

    def get_photo(photo_id: str):
        rec = booth.store.get(photo_id) if valid_id(photo_id) else None
        if not rec:
            raise HTTPException(status_code=404, detail="Photo not found")
        return rec

    # -- pages ----------------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/operator", include_in_schema=False)
    async def operator_page():
        return FileResponse(STATIC_DIR / "operator.html")

    @app.get("/display", include_in_schema=False)
    async def display_page():
        return FileResponse(STATIC_DIR / "display.html")

    @app.get("/camera", include_in_schema=False)
    async def camera_page():
        return FileResponse(STATIC_DIR / "camera.html")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "ai": booth.ai.mode_label}

    # -- API ------------------------------------------------------------------------------

    @app.get("/api/themes")
    async def themes():
        return all_themes()

    @app.post("/api/auth", dependencies=[Depends(require_pin)])
    async def auth():
        return {"ok": True}

    @app.get("/api/photos", dependencies=[Depends(require_pin)])
    async def photos(limit: int = 40):
        records = await asyncio.to_thread(booth.store.recent, max(1, min(limit, 200)))
        return [r.public() for r in records]

    @app.post("/api/capture", dependencies=[Depends(require_pin)])
    async def capture(photo: UploadFile = File(...)):
        data = await photo.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Photo is too large (max 20 MB)")
        try:
            rec = await booth.ingest(data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return rec.public()

    @app.post("/api/test-ai", dependencies=[Depends(require_pin)])
    async def test_ai():
        """One real generation with a tiny synthetic image, to check the key and model."""
        img = Image.new("RGB", (640, 360), (90, 140, 210))
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        started = time.monotonic()
        try:
            raw = await booth.ai.transform(buf.getvalue(), "Turn this into a snowy mountain landscape.", "16:9")
            await asyncio.to_thread(normalize_jpeg, raw)
        except (AIError, ValueError) as exc:
            return {"ok": False, "mode": booth.ai.mode_label, "error": str(exc)}
        return {"ok": True, "mode": booth.ai.mode_label, "seconds": round(time.monotonic() - started, 1)}

    # -- media ----------------------------------------------------------------------------
    # Photo IDs are random 128-bit values, so these links are only reachable by people
    # who were given them (the QR code or the operator's devices).

    no_store = {"Cache-Control": "no-store"}
    cache_forever = {"Cache-Control": "public, max-age=31536000, immutable"}

    @app.get("/media/{photo_id}/{kind}.jpg", include_in_schema=False)
    async def media(photo_id: str, kind: str, request: Request):
        rec = get_photo(photo_id)
        if kind == "original":
            return FileResponse(booth.store.path(rec.id, "original"), headers=cache_forever)
        if kind == "thumb":
            return Response(await asyncio.to_thread(_thumbnail, booth, rec), media_type="image/jpeg")
        if rec.status != "done":
            raise HTTPException(status_code=404, detail="Photo is not ready yet")
        if kind == "result":
            return FileResponse(booth.store.path(rec.id, "result"), headers=no_store)
        if kind == "print":
            prefs = booth.prefs
            qr_url = f"{base_url(request)}/p/{rec.id}" if prefs.print_qr else None
            taken = datetime.fromtimestamp(rec.created_at, tz)
            date_text = f"{taken.day} {taken:%b %Y}"
            data = await asyncio.to_thread(
                compose_print,
                booth.store.path(rec.id, "result").read_bytes(),
                get_theme(rec.theme_id),
                prefs.event_name,
                date_text,
                rec.orientation,
                qr_url,
            )
            return Response(data, media_type="image/jpeg", headers=no_store)
        raise HTTPException(status_code=404)

    @app.get("/samples/{theme_id}.jpg", include_in_schema=False)
    async def sample(theme_id: str):
        path = booth.sample_path(theme_id) if theme_id in booth.samples else None
        if not path or not path.exists():
            raise HTTPException(status_code=404)
        return FileResponse(path, headers=cache_forever)  # URL carries a version

    @app.get("/qr/{photo_id}.svg", include_in_schema=False)
    async def qr(photo_id: str, request: Request):
        rec = get_photo(photo_id)
        buf = io.BytesIO()
        segno.make(f"{base_url(request)}/p/{rec.id}", error="m").save(buf, kind="svg", scale=8, border=2)
        return Response(buf.getvalue(), media_type="image/svg+xml", headers=cache_forever)

    @app.get("/p/{photo_id}", response_class=HTMLResponse, include_in_schema=False)
    async def guest_page(photo_id: str):
        rec = get_photo(photo_id)
        page = (STATIC_DIR / "guest.html").read_text()
        data = {
            "event_name": booth.prefs.event_name,
            "theme_name": get_theme(rec.theme_id).name,
            "ready": rec.status == "done",
            "result_url": f"/media/{rec.id}/result.jpg?v={rec.version}",
            "print_url": f"/media/{rec.id}/print.jpg?v={rec.version}",
            "file_stem": f"funbooth-{rec.id[:8]}",
        }
        page = page.replace("{{TITLE}}", html.escape(booth.prefs.event_name or "Fun Booth"))
        # json.dumps output can't break out of the <script> block once "</" is escaped.
        page = page.replace("{{DATA}}", json.dumps(data).replace("</", "<\\/"))
        return HTMLResponse(page, headers=no_store)

    # -- live sync ------------------------------------------------------------------------

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, role: str = "display", pin: str = ""):
        await ws.accept()
        if role not in ROLES or not pin_ok(pin):
            await ws.close(code=4401, reason="Wrong PIN")
            return
        client_id = await booth.connect(ws, role)
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:  # live preview frame from the camera
                    await booth.relay_frame(client_id, message["bytes"])
                    continue
                try:
                    msg = json.loads(message.get("text") or "")
                except ValueError:
                    continue
                await booth.handle(client_id, msg)
        except WebSocketDisconnect:
            pass
        finally:
            await booth.disconnect(client_id)

    return app


def _thumbnail(booth: Booth, rec) -> bytes:
    kind = "result" if rec.status == "done" else "original"
    cached = booth.store.path(rec.id, f"thumb-{kind}-{rec.version}")
    if cached.exists():
        return cached.read_bytes()
    data = normalize_jpeg(booth.store.path(rec.id, kind).read_bytes(), THUMB_SIZE, 80)
    cached.write_bytes(data)
    return data
