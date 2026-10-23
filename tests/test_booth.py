import asyncio
import base64
import io
import json
import re
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from app.ai import AIError, ImageAI
from app.reveal import make_reveal_gif
from app.video import VideoAI
from app.booth import GUEST_THEME_IDS, Prefs
from app.config import DEFAULT_MODEL, Settings
from app.main import create_app
from app.printing import compose_print
from app.themes import FACE_FRAMING, FACE_FRAMING_END, FULL_BODY_FRAMING, IDENTITY_GUARD, PLACE_INTEGRATION, REALISM, THEMES, build_prompt, get_theme

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
        video_models=("bytedance/seedance-1-5-pro", "x-ai/grok-imagine-video-1.5-lite"),
        video_resolution="720p",
        video_seconds=5,
        video_timeout_seconds=30,
        booth_pin=PIN,
        default_event_name="Test Party",
        data_dir=tmp_path,
        public_url="https://booth.test",
    )


# -- prompts -----------------------------------------------------------------------------


def test_prompts_lock_faces_and_fit_the_place():
    winter = build_prompt(get_theme("winter"), "add a snowman")
    assert winter.startswith(IDENTITY_GUARD) and winter.endswith(REALISM)
    assert FULL_BODY_FRAMING in winter and PLACE_INTEGRATION in winter
    assert "snowy pine forest" in winter and "Also: add a snowman" in winter

    # Every theme works as a full-body shot or a face-only close-up.
    noir = build_prompt(get_theme("noir"), framing="face")
    assert FACE_FRAMING in noir and noir.endswith(FACE_FRAMING_END + REALISM)
    assert FULL_BODY_FRAMING not in noir and PLACE_INTEGRATION not in noir
    assert "black and white" in noir
    beach_close_up = build_prompt(get_theme("sun"), framing="face")
    assert FACE_FRAMING in beach_close_up and PLACE_INTEGRATION in beach_close_up

    custom = build_prompt(get_theme("custom"), "a pirate ship deck")
    assert custom == IDENTITY_GUARD + FULL_BODY_FRAMING + "a pirate ship deck" + REALISM
    ids = {t.id for t in THEMES}
    assert {"fashion", "noir", "mountains", "kawaii", "classroom"} <= ids
    assert not {"lunar", "lights", "xmas"} & ids  # religious festivals are off for now
    assert get_theme("xmas").id == "winter"  # old saved prefs fall back safely


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


# -- video clips -------------------------------------------------------------------------


def fake_video_api(script):
    """MockTransport for /videos: `script` maps a model id to "ok", "refuse" or "fail"."""
    calls = []

    def handler(request: httpx.Request):
        path = request.url.path
        calls.append((request.method, request.url.host, path, request.headers.get("authorization")))
        if request.method == "POST":
            body = json.loads(request.content)
            outcome = script[body["model"]]
            if outcome == "refuse":
                return httpx.Response(400, json={"error": {"message": "The input image may contain real person"}})
            job = body["model"].split("/")[-1]
            return httpx.Response(202, json={"id": job, "polling_url": f"https://openrouter.test/api/v1/videos/{job}", "status": "pending"})
        if path.endswith("/content") or request.url.host == "cdn.example":
            return httpx.Response(200, content=b"MP4DATA", headers={"content-type": "video/mp4"})
        job = path.rsplit("/", 1)[-1]
        model = next(m for m in script if m.endswith(job))
        if script[model] == "fail":
            return httpx.Response(200, json={"id": job, "polling_url": path, "status": "failed", "error": "moderation"})
        return httpx.Response(200, json={
            "id": job, "polling_url": path, "status": "completed", "usage": {"cost": 0.06},
            "unsigned_urls": [f"https://openrouter.test/api/v1/videos/{job}/content?index=0"],
        })

    return handler, calls


def video_ai(settings, handler):
    keyed = replace(settings, openrouter_api_key="sk-test")
    return VideoAI(keyed, httpx.AsyncClient(transport=httpx.MockTransport(handler)), poll_interval=0)


def test_video_job_is_submitted_polled_and_downloaded(settings):
    bodies = []
    handler, calls = fake_video_api({"bytedance/seedance-1-5-pro": "ok", "x-ai/grok-imagine-video-1.5-lite": "ok"})

    def spy(request):
        if request.method == "POST":
            bodies.append(json.loads(request.content))
        return handler(request)

    clip = run(video_ai(settings, spy).animate(jpeg(), "they wave", "3:4"))
    assert (clip.data, clip.model, clip.cost) == (b"MP4DATA", "bytedance/seedance-1-5-pro", 0.06)
    body = bodies[0]
    assert body["duration"] == 5 and body["resolution"] == "720p" and body["aspect_ratio"] == "3:4"
    assert body["generate_audio"] is False
    frame = body["frame_images"][0]
    assert frame["frame_type"] == "first_frame" and frame["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert [c[0] for c in calls] == ["POST", "GET", "GET"]
    assert all(auth == "Bearer sk-test" for *_, auth in calls)


def test_video_falls_back_when_a_model_refuses_real_people(settings):
    handler, calls = fake_video_api({"bytedance/seedance-1-5-pro": "refuse", "x-ai/grok-imagine-video-1.5-lite": "ok"})
    clip = run(video_ai(settings, handler).animate(jpeg(), "p", "16:9"))
    assert clip.model == "x-ai/grok-imagine-video-1.5-lite"
    assert [c[0] for c in calls] == ["POST", "POST", "GET", "GET"]


def test_video_reports_every_model_when_all_fail(settings):
    handler, _ = fake_video_api({"bytedance/seedance-1-5-pro": "refuse", "x-ai/grok-imagine-video-1.5-lite": "fail"})
    with pytest.raises(AIError) as exc:
        run(video_ai(settings, handler).animate(jpeg(), "p", "16:9"))
    assert "real person" in str(exc.value) and "moderation" in str(exc.value)


def test_video_download_never_sends_the_key_elsewhere(settings):
    handler, calls = fake_video_api({"bytedance/seedance-1-5-pro": "ok", "x-ai/grok-imagine-video-1.5-lite": "ok"})

    def cdn(request):
        response = handler(request)
        if request.method == "GET" and request.url.host == "openrouter.test" and not request.url.path.endswith("/content"):
            data = response.json()
            data["unsigned_urls"] = ["https://cdn.example/clip.mp4"]
            return httpx.Response(200, json=data)
        return response

    run(video_ai(settings, cdn).animate(jpeg(), "p", "16:9"))
    assert [auth for _, host, _, auth in calls if host == "cdn.example"] == [None]


def test_before_after_gif():
    data = make_reveal_gif(jpeg(1600, 900, (10, 10, 10)), jpeg(1600, 900, (250, 250, 250)))
    gif = Image.open(io.BytesIO(data))
    assert gif.format == "GIF" and gif.size == (480, 270) and gif.n_frames > 10
    assert gif.info["loop"] == 0


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
    with TestClient(create_app(settings, ai, VideoAI(settings, poll_interval=0))) as c:
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
        assert photo["theme_id"] == "sun" and photo["framing"] == "full"
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

        # Restyle the same photo with another theme, as a face-only close-up.
        op.send_json({"type": "prefs", "prefs": {"theme_id": "80s", "framing": "face"}})
        op.send_json({"type": "regenerate", "photo_id": photo_id})
        again = receive_until(op, lambda m: m["type"] == "state" and m["phase"] == "result" and m["photo"]["version"] == 2)
        assert again["photo"]["theme_id"] == "80s" and again["photo"]["framing"] == "face"

        listed = client.get("/api/photos", headers=headers).json()
        assert [p["id"] for p in listed] == [photo_id]

        # Guests clear their own result screen.
        disp.send_json({"type": "reset"})
        idle = receive_until(op, is_state(phase="idle"))
        assert idle["photo"] is None and idle["qr"] is None

    # Prefs survive a restart.
    assert json.loads((client.app.state.booth.settings.data_dir / "prefs.json").read_text())["event_name"] == "Joe's Party"


def test_booth_modes_pick_the_camera():
    prefs = Prefs()
    assert (prefs.mode, prefs.camera_source) == ("two_ipads", "operator")
    prefs.update({"mode": "solo"})
    assert prefs.camera_source == "display"
    prefs.update({"mode": "laptop"})
    assert prefs.camera_source == "camera"
    prefs.update({"camera_source": "operator"})  # laptop's own or USB camera
    assert prefs.mode == "laptop"
    prefs.update({"mode": "two_ipads"})
    assert prefs.camera_source == "operator"
    prefs.update({"camera_source": "display"})
    assert prefs.mode == "solo"
    prefs.update({"camera_source": "operator"})
    assert prefs.mode == "two_ipads"

    saved_before_modes = Prefs()
    saved_before_modes.update({"camera_source": "camera"})
    assert saved_before_modes.mode == "laptop"


def test_each_mode_shoots_with_its_camera(client):
    with connect(client, "operator") as op, connect(client, "display") as disp, connect(client, "camera") as cam:
        ids = {"operator": welcome(op), "display": welcome(disp), "camera": welcome(cam)}
        for ws in (op, disp, cam):
            ws.send_json({"type": "camera", "ready": True})
        expected = {"solo": "display", "laptop": "camera", "two_ipads": "operator"}
        for mode, device in expected.items():
            # The guest iPad's start screen sends the mode with the PIN.
            disp.send_json({"type": "prefs", "pin": PIN, "prefs": {"mode": mode}})
            receive_until(op, lambda m, mode=mode, cam_id=ids[device]: m["type"] == "state" and m["prefs"]["mode"] == mode and m["camera_id"] == cam_id)
            disp.send_json({"type": "start"})
            assert receive_until(op, lambda m: m["type"] == "countdown")["capturer"] == ids[device]
            op.send_json({"type": "reset"})
            receive_until(op, is_state(phase="idle"))


def test_guests_choose_themes_but_cannot_run_the_booth(client):
    with connect(client, "operator") as op, connect(client, "display") as disp:
        welcome(op)
        display_id = welcome(disp)

        disp.send_json({"type": "theme", "theme_id": "90s"})
        receive_until(op, lambda m: m["type"] == "state" and m["prefs"]["theme_id"] == "90s")

        op.send_json({"type": "prefs", "prefs": {"guest_themes": ["kawaii", "winter", "not-a-theme"]}})
        state = receive_until(disp, lambda m: m["type"] == "state" and m["prefs"]["guest_themes"] != GUEST_THEME_IDS)
        assert state["prefs"]["guest_themes"] == ["winter", "kawaii"]  # catalogue order, unknown ids dropped

        # Hidden themes, operator-only messages and prefs without the PIN are all ignored.
        disp.send_json({"type": "theme", "theme_id": "sun"})
        disp.send_json({"type": "prefs", "prefs": {"event_name": "hacked"}})
        disp.send_json({"type": "send_qr", "photo_id": "0" * 32})
        disp.send_json({"type": "framing", "framing": "everything"})
        disp.send_json({"type": "theme", "theme_id": "kawaii"})
        state = receive_until(disp, lambda m: m["type"] == "state" and m["prefs"]["theme_id"] == "kawaii")
        assert state["prefs"]["event_name"] == "Test Party"
        assert state["prefs"]["framing"] == "full"

        # Guests choose full body or face only for any theme.
        disp.send_json({"type": "framing", "framing": "face"})
        assert receive_until(disp, lambda m: m["type"] == "state" and m["prefs"]["framing"] == "face")

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
        assert state["samples"]["winter"].startswith("/samples/")  # made in the app beats the built-in one
        assert state["samples"]["sun"] == "/static/samples/sun.jpg"  # built-in default from static/samples

        op.send_json({"type": "make_samples", "photo_id": photo_id})
        receive_until(op, is_state(making_samples=True))
        done = receive_until(op, is_state(making_samples=False), limit=200)
        assert all(done["samples"][t] for t in GUEST_THEME_IDS)
        assert "All theme samples are ready" in receive_until(op, lambda m: m["type"] == "toast")["text"]

    assert client.get("/samples/nope.jpg").status_code == 404


def test_video_clip_and_gif_for_a_photo(client):
    headers = {"X-Booth-Pin": PIN}
    with connect(client, "operator") as op:
        welcome(op)
        photo_id = client.post("/api/capture", headers=headers, files={"photo": ("c.jpg", jpeg(1920, 1080))}).json()["id"]
        photo = receive_until(op, is_state(phase="result"))["photo"]
        assert photo["video_url"] is None

        gif = client.get(photo["reveal_url"])
        assert gif.headers["content-type"] == "image/gif"
        assert Image.open(io.BytesIO(gif.content)).n_frames > 10

        op.send_json({"type": "make_video", "photo_id": photo_id})
        receive_until(op, lambda m: m["type"] == "photo" and m["photo"]["video_status"] == "processing")
        done = receive_until(op, lambda m: m["type"] == "state" and m["photo"]["video_status"] == "done")["photo"]
        assert done["video_model"] == "mock"

        # iPhones fetch video in byte ranges.
        part = client.get(done["video_url"], headers={"Range": "bytes=0-99"})
        assert part.status_code == 206 and part.headers["content-type"] == "video/mp4" and len(part.content) == 100
        assert done["video_url"] in client.get(f"/p/{photo_id}").text

        # Restyling makes the old clip stale.
        op.send_json({"type": "regenerate", "photo_id": photo_id})
        restyled = receive_until(op, lambda m: m["type"] == "state" and m["photo"]["version"] == 2 and m["phase"] == "result")
        assert restyled["photo"]["video_status"] == "" and restyled["photo"]["video_url"] is None


def test_auto_video_makes_a_clip_for_every_photo(client):
    with connect(client, "operator") as op:
        welcome(op)
        op.send_json({"type": "prefs", "prefs": {"auto_video": True}})
        receive_until(op, lambda m: m["type"] == "state" and m["prefs"]["auto_video"])
        client.post("/api/capture", headers={"X-Booth-Pin": PIN}, files={"photo": ("c.jpg", jpeg())})
        receive_until(op, lambda m: m["type"] == "state" and m["photo"] and m["photo"]["video_status"] == "done", limit=80)


def test_restart_recovers_interrupted_work(settings):
    from app.storage import PhotoStore

    store = PhotoStore(settings.data_dir)
    rec = store.create(jpeg(), "winter", "", "landscape")
    rec.status, rec.video_status = "done", "processing"
    store.save(rec)
    stuck = store.create(jpeg(), "winter", "", "landscape")  # left "processing"

    with TestClient(create_app(settings)):
        pass
    assert store.get(rec.id).video_status == "error"
    assert store.get(stuck.id).status == "error"


def test_new_themes_show_up_for_guests_after_an_update(settings):
    prefs_path = settings.data_dir / "prefs.json"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # Saved by an older version, with the operator hiding 80s and Christmas.
    old = ["winter", "sun", "mountains", "festival", "lunar", "lights", "90s", "y2k", "hollywood", "fashion", "noir"]
    prefs_path.write_text(json.dumps({"guest_themes": old, "theme_id": "xmas"}))
    with TestClient(create_app(settings)) as client:
        prefs = client.app.state.booth.prefs
        assert "kawaii" in prefs.guest_themes and "classroom" in prefs.guest_themes
        assert "80s" not in prefs.guest_themes and "lunar" not in prefs.guest_themes
        assert prefs.theme_id == "winter"
        prefs.update({"guest_themes": [t for t in GUEST_THEME_IDS if t != "kawaii"]})
        client.app.state.booth._save_prefs()
    # Once saved with the current catalogue, a theme the operator hid stays hidden.
    with TestClient(create_app(settings)) as client:
        assert "kawaii" not in client.app.state.booth.prefs.guest_themes


def test_pages_load_assets_from_versioned_urls(client):
    """A new deploy must never be mixed with CSS/JS cached from an older one."""
    page = client.get("/display")
    assert page.headers["cache-control"] == "no-cache"
    assert '"/static/display.css"' not in page.text
    css = re.search(r'href="(/v/[0-9a-f]+/display\.css)"', page.text).group(1)
    js = re.search(r'src="(/v/[0-9a-f]+/display\.js)"', page.text).group(1)
    assert "immutable" in client.get(css).headers["cache-control"]
    script = client.get(js)
    assert "javascript" in script.headers["content-type"]
    assert 'from "./common.js"' in script.text  # resolves inside the same version
    assert client.get(js.replace("display.js", "common.js")).status_code == 200

    assert client.get("/v/old/display.css").headers["cache-control"] == "no-cache"
    assert client.get("/v/x/%2e%2e/%2e%2e/app/main.py").status_code == 404
    assert client.get("/static/app.css").headers["cache-control"] == "no-cache"
    for path in ("/", "/operator", "/camera"):
        assert '"/static/' not in client.get(path).text


def test_bad_uploads_and_unknown_photos(client):
    headers = {"X-Booth-Pin": PIN}
    assert client.post("/api/capture", headers=headers, files={"photo": ("x.jpg", b"not an image")}).status_code == 400
    assert client.get("/media/../../etc/passwd/original.jpg").status_code == 404
    assert client.get("/media/" + "0" * 32 + "/result.jpg").status_code == 404
    assert client.get("/p/nope").status_code == 404
