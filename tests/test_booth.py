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
from app.booth import GUEST_THEME_IDS
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


def test_text_to_image_sends_no_input_photo(settings):
    bodies = []
    out = jpeg(color=(4, 5, 6))

    def handler(request: httpx.Request):
        bodies.append(json.loads(request.content))
        if request.url.path.endswith("/images"):
            return httpx.Response(422, json={"error": {"message": "nope"}})
        url = "data:image/jpeg;base64," + base64.b64encode(out).decode()
        return httpx.Response(200, json={"choices": [{"message": {"images": [{"image_url": {"url": url}}]}}]})

    ai = ImageAI(replace(settings, openrouter_api_key="sk-test"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert run(ai.create("four friends at a party", "16:9")) == out
    images_body, chat_body = bodies
    assert "input_references" not in images_body and images_body["prompt"] == "four friends at a party"
    assert chat_body["messages"][0]["content"] == [{"type": "text", "text": "four friends at a party"}]


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


def receive_until(ws, predicate, limit=40):
    """Next JSON message matching `predicate` (binary preview frames are skipped)."""
    for _ in range(limit):
        msg = ws.receive()
        if msg.get("text") is None:
            continue
        data = json.loads(msg["text"])
        if predicate(data):
            return data
    raise AssertionError("expected message never arrived")


def connect(client, role):
    return client.websocket_connect(f"/ws?role={role}&pin={PIN}")


def welcome(ws) -> str:
    return receive_until(ws, lambda m: m["type"] == "welcome")["client_id"]


def is_state(**expected):
    return lambda m: m["type"] == "state" and all(m.get(k) == v for k, v in expected.items())


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

    with connect(client, "operator") as op, connect(client, "display") as disp:
        welcome(op)
        display_id = welcome(disp)

        # The operator's own camera is the default, and it isn't on yet.
        op.send_json({"type": "start"})
        assert "operator camera isn't ready" in receive_until(op, lambda m: m["type"] == "toast")["text"]

        op.send_json({"type": "prefs", "prefs": {"camera_source": "display", "theme_id": "sun", "event_name": "Joe's Party"}})
        disp.send_json({"type": "camera", "ready": True})
        receive_until(op, is_state(camera_id=display_id))

        op.send_json({"type": "start"})
        countdown = receive_until(disp, lambda m: m["type"] == "countdown")
        assert countdown["capturer"] == display_id
        assert countdown["seconds"] == 3

        # The camera device uploads its frame after the countdown.
        res = client.post("/api/capture", headers=headers, files={"photo": ("c.jpg", jpeg(1920, 1080))})
        assert res.status_code == 200
        photo_id = res.json()["id"]

        photo = receive_until(op, is_state(phase="result"))["photo"]
        assert photo["id"] == photo_id
        assert photo["status"] == "done"
        assert photo["theme_id"] == "sun"
        receive_until(disp, is_state(phase="result"))

        assert client.get(photo["result_url"]).headers["content-type"] == "image/jpeg"
        assert client.get(photo["thumb_url"]).status_code == 200
        printed = Image.open(io.BytesIO(client.get(photo["print_url"]).content))
        assert printed.size == (1800, 1200)
        assert client.get(photo["qr_url"]).headers["content-type"] == "image/svg+xml"
        page = client.get(f"/p/{photo_id}").text
        assert "Joe&#x27;s Party" in page and '"ready": true' in page

        # The operator sends the download QR to the guest screen.
        op.send_json({"type": "send_qr", "photo_id": photo_id})
        assert receive_until(disp, lambda m: m["type"] == "state" and m["qr"])["qr"]["id"] == photo_id

        # Restyle the same photo with another theme.
        op.send_json({"type": "prefs", "prefs": {"theme_id": "80s"}})
        op.send_json({"type": "regenerate", "photo_id": photo_id})
        again = receive_until(op, lambda m: m["type"] == "state" and m["phase"] == "result" and m["photo"]["version"] == 2)
        assert again["photo"]["theme_id"] == "80s"

        listed = client.get("/api/photos", headers=headers).json()
        assert [p["id"] for p in listed] == [photo_id]

        # Guests clear their own result screen.
        disp.send_json({"type": "reset"})
        idle = receive_until(op, is_state(phase="idle"))
        assert idle["photo"] is None and idle["qr"] is None

    # Prefs survive a restart.
    assert json.loads((client.app.state.booth.settings.data_dir / "prefs.json").read_text())["event_name"] == "Joe's Party"


def test_guests_choose_themes_but_cannot_run_the_booth(client):
    with connect(client, "operator") as op, connect(client, "display") as disp:
        welcome(op)
        display_id = welcome(disp)

        disp.send_json({"type": "theme", "theme_id": "90s"})
        receive_until(op, lambda m: m["type"] == "state" and m["prefs"]["theme_id"] == "90s")

        op.send_json({"type": "prefs", "prefs": {"guest_themes": ["xmas", "winter", "not-a-theme"]}})
        state = receive_until(disp, lambda m: m["type"] == "state" and m["prefs"]["guest_themes"] != GUEST_THEME_IDS)
        assert state["prefs"]["guest_themes"] == ["winter", "xmas"]  # catalogue order, unknown ids dropped

        # Hidden themes, operator-only messages and prefs without the PIN are all ignored.
        disp.send_json({"type": "theme", "theme_id": "sun"})
        disp.send_json({"type": "prefs", "prefs": {"event_name": "hacked"}})
        disp.send_json({"type": "send_qr", "photo_id": "0" * 32})
        disp.send_json({"type": "theme", "theme_id": "xmas"})
        state = receive_until(disp, lambda m: m["type"] == "state" and m["prefs"]["theme_id"] == "xmas")
        assert state["prefs"]["event_name"] == "Test Party"

        # With the PIN (the host menu on a one-iPad booth) the guest screen can change settings.
        disp.send_json({"type": "prefs", "pin": PIN, "prefs": {"camera_source": "display"}})
        disp.send_json({"type": "camera", "ready": True})
        receive_until(disp, is_state(camera_id=display_id))

        # Guests start the countdown themselves, but can't cancel it.
        disp.send_json({"type": "start"})
        assert receive_until(disp, lambda m: m["type"] == "countdown")["capturer"] == display_id
        disp.send_json({"type": "reset"})
        op.send_json({"type": "prefs", "prefs": {"countdown": 5}})
        assert receive_until(op, lambda m: m["type"] == "state" and m["prefs"]["countdown"] == 5)["phase"] == "countdown"


def test_phone_camera_streams_preview_to_guest_screen(client):
    with connect(client, "operator") as op, connect(client, "display") as disp, connect(client, "camera") as cam:
        welcome(op)
        welcome(disp)
        camera_id = welcome(cam)

        op.send_json({"type": "prefs", "prefs": {"camera_source": "camera"}})
        cam.send_json({"type": "camera", "ready": True})
        receive_until(op, is_state(camera_id=camera_id))

        disp.send_json({"type": "preview", "want": True})
        receive_until(cam, is_state(preview_wanted=True))

        frame = jpeg(64, 36)
        cam.send_bytes(frame)
        for _ in range(40):
            msg = disp.receive()
            if msg.get("bytes") is not None:
                assert msg["bytes"] == frame
                break
        else:
            raise AssertionError("preview frame never reached the guest screen")

        # The phone's shutter button starts the countdown and the phone shoots.
        cam.send_json({"type": "start"})
        assert receive_until(disp, lambda m: m["type"] == "countdown")["capturer"] == camera_id


def test_theme_samples(client):
    headers = {"X-Booth-Pin": PIN}
    with connect(client, "operator") as op:
        welcome(op)
        photo_id = client.post("/api/capture", headers=headers, files={"photo": ("c.jpg", jpeg(1920, 1080))}).json()["id"]
        photo = receive_until(op, is_state(phase="result"))["photo"]
        assert photo["theme_id"] == "winter"

        op.send_json({"type": "set_sample", "photo_id": photo_id})
        state = receive_until(op, lambda m: m["type"] == "state" and m["samples"]["winter"])
        assert client.get(state["samples"]["winter"]).headers["content-type"] == "image/jpeg"
        assert state["samples"]["sun"] is None

        op.send_json({"type": "make_samples", "photo_id": photo_id})
        receive_until(op, is_state(making_samples=True))
        done = receive_until(op, is_state(making_samples=False), limit=200)
        assert all(done["samples"][t] for t in GUEST_THEME_IDS)
        assert "All theme samples are ready" in receive_until(op, lambda m: m["type"] == "toast")["text"]

    assert client.get("/samples/nope.jpg").status_code == 404


def test_bad_uploads_and_unknown_photos(client):
    headers = {"X-Booth-Pin": PIN}
    assert client.post("/api/capture", headers=headers, files={"photo": ("x.jpg", b"not an image")}).status_code == 400
    assert client.get("/media/../../etc/passwd/original.jpg").status_code == 404
    assert client.get("/media/" + "0" * 32 + "/result.jpg").status_code == 404
    assert client.get("/p/nope").status_code == 404
