"""OpenRouter image editing (Seedream 5.0 Flash by default).

Two request styles are supported because OpenRouter exposes image models through both:

* ``POST /images`` - the unified image API (``input_references`` + ``data[].b64_json``)
* ``POST /chat/completions`` with ``modalities`` - images come back in ``message.images``

``OPENROUTER_API_MODE=auto`` (the default) tries ``/images`` first and falls back to chat
completions if the request shape is rejected.
"""

from __future__ import annotations

import asyncio
import base64
import colorsys
import hashlib
import io
import logging
import os

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from .config import Settings

log = logging.getLogger("funbooth.ai")

# Status codes where trying the other request style might help.
_SHAPE_ERRORS = {400, 404, 405, 415, 422}


class AIError(Exception):
    """Raised with a message that is safe to show to the operator."""


def to_data_url(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def images_payload(model: str, prompt: str, data_url: str | None, aspect_ratio: str, resolution: str) -> dict:
    payload = {"model": model, "prompt": prompt, "aspect_ratio": aspect_ratio, "n": 1}
    if data_url:
        payload["input_references"] = [{"type": "image_url", "image_url": {"url": data_url}}]
    if resolution:
        payload["resolution"] = resolution
    return payload


def chat_payload(model: str, prompt: str, data_url: str | None, aspect_ratio: str) -> dict:
    content = [{"type": "text", "text": prompt}]
    if data_url:
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    return {
        "model": model,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": content}],
        "image_config": {"aspect_ratio": aspect_ratio},
    }


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body)
        if isinstance(err, dict):
            msg = err.get("message") or str(err)
        else:
            msg = str(err)
    except ValueError:
        msg = resp.text[:300]
    return f"OpenRouter returned {resp.status_code}: {msg}"


class ImageAI:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self.mock_delay = float(os.getenv("MOCK_DELAY", "2.5"))
        # In auto mode, remember which request style worked so later calls skip the probe.
        self._working_mode: str | None = None

    async def aclose(self) -> None:
        await self.client.aclose()

    @property
    def mode_label(self) -> str:
        if self.settings.mock_ai:
            return "mock (no API key)"
        return self.settings.model.split("/")[-1]

    async def transform(self, image_jpeg: bytes, prompt: str, aspect_ratio: str) -> bytes:
        """Return the edited image as raw bytes (PNG or JPEG)."""
        if self.settings.mock_ai:
            return await self._mock(image_jpeg, prompt)
        return await self._request(prompt, to_data_url(image_jpeg), aspect_ratio)

    async def create(self, prompt: str, aspect_ratio: str) -> bytes:
        """Text-to-image, with no input photo (used to make demo photos for samples)."""
        if self.settings.mock_ai:
            return await self._mock(_blank_jpeg(aspect_ratio), prompt)
        return await self._request(prompt, None, aspect_ratio)

    async def _request(self, prompt: str, data_url: str | None, aspect_ratio: str) -> bytes:
        mode = self._working_mode or self.settings.api_mode
        if mode == "chat":
            return await self._via_chat(prompt, data_url, aspect_ratio)
        if mode == "images":
            return await self._via_images(prompt, data_url, aspect_ratio)

        try:
            result = await self._via_images(prompt, data_url, aspect_ratio)
            self._working_mode = "images"
            return result
        except _ShapeRejected as first:
            log.warning("/images rejected the request (%s); retrying via chat completions", first)
            try:
                result = await self._via_chat(prompt, data_url, aspect_ratio)
            except AIError as second:
                raise AIError(f"{first} (chat fallback also failed: {second})") from second
            self._working_mode = "chat"
            return result

    # -- request styles -------------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "HTTP-Referer": self.settings.public_url or "https://funbooth.local",
            "X-Title": "Fun Booth",
        }

    async def _post(self, path: str, payload: dict) -> httpx.Response:
        url = f"{self.settings.openrouter_base_url}{path}"
        try:
            return await self.client.post(url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise AIError("The AI took too long to respond. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise AIError(f"Could not reach OpenRouter: {exc}") from exc

    async def _via_images(self, prompt: str, data_url: str | None, aspect_ratio: str) -> bytes:
        payload = images_payload(self.settings.model, prompt, data_url, aspect_ratio, self.settings.resolution)
        resp = await self._post("/images", payload)
        if resp.status_code in _SHAPE_ERRORS:
            raise _ShapeRejected(_error_message(resp))
        if resp.status_code >= 400:
            raise AIError(_error_message(resp))

        items = resp.json().get("data") or []
        if not items:
            raise _ShapeRejected("no images in /images response")
        item = items[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            return await self._fetch_image(item["url"])
        raise _ShapeRejected("unrecognised /images response")

    async def _via_chat(self, prompt: str, data_url: str | None, aspect_ratio: str) -> bytes:
        payload = chat_payload(self.settings.model, prompt, data_url, aspect_ratio)
        resp = await self._post("/chat/completions", payload)
        if resp.status_code >= 400:
            raise AIError(_error_message(resp))

        body = resp.json()
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIError("OpenRouter returned no result.") from exc
        for image in message.get("images") or []:
            ref = image.get("image_url") or image.get("imageUrl") or {}
            url = ref.get("url") if isinstance(ref, dict) else ref
            if url:
                return await self._fetch_image(url)
        text = (message.get("content") or "").strip()
        raise AIError(f"The model did not return an image. {text[:200]}".strip())

    async def _fetch_image(self, url: str) -> bytes:
        if url.startswith("data:"):
            return base64.b64decode(url.split(",", 1)[1])
        resp = await self.client.get(url)
        if resp.status_code >= 400:
            raise AIError(f"Could not download the generated image ({resp.status_code}).")
        return resp.content

    # -- mock -----------------------------------------------------------------------------

    async def _mock(self, image_jpeg: bytes, prompt: str) -> bytes:
        """Fake 'AI' so the whole booth can be tested without spending credits."""
        await asyncio.sleep(self.mock_delay)
        return await asyncio.to_thread(_mock_effect, image_jpeg, prompt)


class _ShapeRejected(AIError):
    """The endpoint did not accept or understand our request shape."""


def _blank_jpeg(aspect_ratio: str) -> bytes:
    w, h = (int(x) for x in aspect_ratio.split(":"))
    buf = io.BytesIO()
    Image.new("RGB", (1024, round(1024 * h / w)), (128, 128, 128)).save(buf, "JPEG")
    return buf.getvalue()


def _mock_effect(image_jpeg: bytes, prompt: str) -> bytes:
    hue = int(hashlib.sha1(prompt.encode()).hexdigest()[:4], 16) / 0xFFFF
    dark = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.85, 0.35))
    light = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.12) % 1, 0.35, 1.0))

    img = Image.open(io.BytesIO(image_jpeg)).convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageOps.colorize(img, black=dark, white=light).convert("RGB")

    draw = ImageDraw.Draw(img)
    label = "MOCK AI PREVIEW"
    font = ImageFont.load_default(size=max(16, img.width // 30))
    pad = max(12, img.width // 60)
    box = draw.textbbox((0, 0), label, font=font)
    draw.rectangle((pad, pad, pad * 3 + box[2], pad * 3 + box[3]), fill=(0, 0, 0))
    draw.text((pad * 2, pad * 2), label, fill=(255, 255, 255), font=font)

    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()
