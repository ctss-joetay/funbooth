import asyncio
import base64
import io
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from app.ai import AIError, ImageAI
from app.config import DEFAULT_MODEL, Settings
from app.main import create_app
from app.printing import compose_print
from app.themes import IDENTITY_GUARD, build_prompt, get_theme

PIN = "1234"


def jpeg(width=320, height=180, color=(200, 80, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        openrouter_api_key="",
        openrouter_base_url="https://openrouter.test/api/v1",
        model=DEFAULT_MODEL,
        api_mode="auto",
        resolution="2K",
        timeout_seconds=10,
        booth_pin=PIN,
        default_event_name="Test Party",
        data_dir=tmp_path,
        public_url="https://booth.test",
    )


# -- prompts -----------------------------------------------------------------------------


def test_prompts_keep_identity_and_append_extras():
    winter = build_prompt(get_theme("winter"), "add a snowman")
    assert winter.startswith(IDENTITY_GUARD)
    assert "snowy winter landscape" in winter
    assert winter.endswith("Also: add a snowman")

    custom = build_prompt(get_theme("custom"), "a pirate ship deck")
    assert custom == IDENTITY_GUARD + "a pirate ship deck"
    assert get_theme("does-not-exist").id == "winter"


# -- OpenRouter client -------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


def test_images_endpoint_request_and_response(settings):
    seen = {}
    out = jpeg(color=(1, 2, 3))

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(out).decode()}]})

    ai = ImageAI(replace(settings, openrouter_api_key="sk-test"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = run(ai.transform(jpeg(), "make it snowy", "16:9"))

    assert result == out
    assert seen["url"] == "https://openrouter.test/api/v1/images"
    assert seen["auth"] == "Bearer sk-test"
    body = seen["body"]
    assert body["model"] == "bytedance-seed/seedream-5-0-flash"
    assert body["prompt"] == "make it snowy"
    assert body["aspect_ratio"] == "16:9"
    assert body["resolution"] == "2K"
    ref = body["input_references"][0]["image_url"]["url"]
    assert ref.startswith("data:image/jpeg;base64,")


def test_auto_mode_falls_back_to_chat_and_remembers(settings):
    calls = []
    out = jpeg(color=(9, 9, 9))
    data_url = "data:image/png;base64," + base64.b64encode(out).decode()

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        if request.url.path.endswith("/images"):
            return httpx.Response(400, json={"error": {"message": "input_references not supported"}})
        body = json.loads(request.content)
        assert body["modalities"] == ["image", "text"]
        assert body["image_config"] == {"aspect_ratio": "3:4"}
        assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg")
        return httpx.Response(200, json={"choices": [{"message": {"content": "", "images": [{"type": "image_url", "image_url": {"url": data_url}}]}}]})

    ai = ImageAI(replace(settings, openrouter_api_key="sk-test"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert run(ai.transform(jpeg(), "p", "3:4")) == out
    assert run(ai.transform(jpeg(), "p", "3:4")) == out
    assert calls == ["/api/v1/images", "/api/v1/chat/completions", "/api/v1/chat/completions"]


def test_billing_errors_are_reported_without_fallback(settings):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    ai = ImageAI(replace(settings, openrouter_api_key="sk-test"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(AIError, match="402: Insufficient credits"):
        run(ai.transform(jpeg(), "p", "16:9"))
    assert calls == ["/api/v1/images"]


# -- printing ------------------------------------------------------------------------------


@pytest.mark.parametrize("orientation,size", [("landscape", (1800, 1200)), ("portrait", (1200, 1800))])
def test_print_is_4x6_at_300dpi(orientation, size):
    data = compose_print(jpeg(1600, 900), get_theme("80s"), "A very long event name " * 4, "23 Oct 2026", orientation, "https://booth.test/p/x")
    img = Image.open(io.BytesIO(data))
    assert img.size == size
    assert round(img.info["dpi"][0]) == 300


# -- full booth flow -------------------------------------------------------------------------


@pytest.fixture
def client(settings):
    ai = ImageAI(settings)
    ai.mock_delay = 0
    with TestClient(create_app(settings, ai)) as c:
        yield c


def receive_until(ws, predicate, limit=30):
    for _ in range(limit):
        msg = ws.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError("expected message never arrived")


def test_pin_is_required(client):
    assert client.get("/api/photos").status_code == 401
    assert client.post("/api/capture", files={"photo": ("a.jpg", jpeg())}).status_code == 401
    assert client.post("/api/auth", headers={"X-Booth-Pin": PIN}).status_code == 200
    with client.websocket_connect("/ws?role=operator&pin=wrong") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_full_capture_flow(client):
    headers = {"X-Booth-Pin": PIN}
    assert client.get("/healthz").json()["ai"].startswith("mock")

    with client.websocket_connect(f"/ws?role=operator&pin={PIN}") as op, client.websocket_connect(f"/ws?role=display&pin={PIN}") as disp:
        receive_until(op, lambda m: m["type"] == "welcome")
        display_id = receive_until(disp, lambda m: m["type"] == "welcome")["client_id"]

        # Operator can't shoot until the display camera is on.
        op.send_json({"type": "start"})
        assert "isn't ready" in receive_until(op, lambda m: m["type"] == "toast")["text"]

        disp.send_json({"type": "camera", "ready": True})
        receive_until(op, lambda m: m["type"] == "state" and m["devices"]["display_camera"])

        op.send_json({"type": "prefs", "prefs": {"theme_id": "sun", "event_name": "Joe's Party", "countdown": 3}})
        receive_until(op, lambda m: m["type"] == "state" and m["prefs"]["theme_id"] == "sun")

        op.send_json({"type": "start"})
        countdown = receive_until(disp, lambda m: m["type"] == "countdown")
        assert countdown["capturer"] == display_id
        assert countdown["seconds"] == 3

        # The display uploads its frame after the countdown.
        res = client.post("/api/capture", headers=headers, files={"photo": ("c.jpg", jpeg(1920, 1080))})
        assert res.status_code == 200
        photo_id = res.json()["id"]

        done = receive_until(op, lambda m: m["type"] == "state" and m["phase"] == "result")
        photo = done["photo"]
        assert photo["id"] == photo_id
        assert photo["status"] == "done"
        assert photo["theme_id"] == "sun"
        receive_until(disp, lambda m: m["type"] == "state" and m["phase"] == "result")

        assert client.get(photo["result_url"]).headers["content-type"] == "image/jpeg"
        assert client.get(photo["thumb_url"]).status_code == 200
        printed = Image.open(io.BytesIO(client.get(photo["print_url"]).content))
        assert printed.size == (1800, 1200)
        assert client.get(photo["qr_url"]).headers["content-type"] == "image/svg+xml"
        page = client.get(f"/p/{photo_id}").text
        assert "Joe&#x27;s Party" in page and '"ready": true' in page

        # Restyle the same photo with another theme.
        op.send_json({"type": "prefs", "prefs": {"theme_id": "80s"}})
        op.send_json({"type": "regenerate", "photo_id": photo_id})
        again = receive_until(op, lambda m: m["type"] == "state" and m["phase"] == "result" and m["photo"]["version"] == 2)
        assert again["photo"]["theme_id"] == "80s"

        listed = client.get("/api/photos", headers=headers).json()
        assert [p["id"] for p in listed] == [photo_id]

        op.send_json({"type": "reset"})
        idle = receive_until(disp, lambda m: m["type"] == "state" and m["phase"] == "idle")
        assert idle["photo"] is None

    # Prefs survive a restart.
    assert json.loads((client.app.state.booth.settings.data_dir / "prefs.json").read_text())["event_name"] == "Joe's Party"


def test_display_cannot_control_the_booth(client):
    with client.websocket_connect(f"/ws?role=display&pin={PIN}") as disp:
        receive_until(disp, lambda m: m["type"] == "welcome")
        disp.send_json({"type": "prefs", "prefs": {"event_name": "hacked"}})
        disp.send_json({"type": "camera", "ready": True})
        state = receive_until(disp, lambda m: m["type"] == "state" and m["devices"]["display_camera"])
        assert state["prefs"]["event_name"] == "Test Party"


def test_bad_uploads_and_unknown_photos(client):
    headers = {"X-Booth-Pin": PIN}
    assert client.post("/api/capture", headers=headers, files={"photo": ("x.jpg", b"not an image")}).status_code == 400
    assert client.get("/media/../../etc/passwd/original.jpg").status_code == 404
    assert client.get("/media/" + "0" * 32 + "/result.jpg").status_code == 404
    assert client.get("/p/nope").status_code == 404
