"""Turn a finished booth photo into a short video clip with OpenRouter's video API.

POST /videos submits a job with the photo as the first frame, then we poll the job and
download the MP4. Models in OPENROUTER_VIDEO_MODELS are tried in order: if one refuses the
photo (e.g. Seedance 2.x rejects pictures of real people) or no longer exists, the next
one gets a go.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from .ai import AIError, _error_message, to_data_url
from .config import Settings

log = logging.getLogger("funbooth.video")

MOCK_CLIP = Path(__file__).resolve().parent / "assets" / "mock-clip.mp4"
TERMINAL = {"completed", "failed", "cancelled", "expired"}
# Status codes where another model might still work.
_TRY_NEXT = {400, 404, 422}


@dataclass(frozen=True)
class VideoResult:
    data: bytes
    model: str
    cost: float | None


class _ModelRefused(AIError):
    """This model can't make this clip; the next one might."""


def video_payload(model: str, prompt: str, data_url: str, aspect_ratio: str, resolution: str, seconds: int) -> dict:
    return {
        "model": model,
        "prompt": prompt,
        "duration": seconds,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "generate_audio": False,
        "frame_images": [{"type": "image_url", "image_url": {"url": data_url}, "frame_type": "first_frame"}],
    }


class VideoAI:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, poll_interval: float = 5.0):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=60)
        self.poll_interval = poll_interval
        split = urlsplit(settings.openrouter_base_url)
        self.origin = f"{split.scheme}://{split.netloc}/"

    async def aclose(self) -> None:
        await self.client.aclose()

    async def animate(self, image_jpeg: bytes, prompt: str, aspect_ratio: str) -> VideoResult:
        if self.settings.mock_ai:
            await asyncio.sleep(self.poll_interval)
            return VideoResult(MOCK_CLIP.read_bytes(), "mock", 0.0)

        data_url = to_data_url(image_jpeg)
        refusals = []
        for model in self.settings.video_models:
            try:
                return await self._run(model, prompt, data_url, aspect_ratio)
            except _ModelRefused as exc:
                log.warning("video model %s refused: %s", model, exc)
                refusals.append(f"{model.split('/')[-1]}: {exc}")
        raise AIError("No video model could animate this photo. " + " | ".join(refusals))

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "HTTP-Referer": self.settings.public_url or "https://funbooth.local",
            "X-Title": "Fun Booth",
        }

    async def _call(self, method: str, url: str, **kwargs) -> httpx.Response:
        # The API key only ever goes to OpenRouter itself, never to a storage/CDN link.
        same_host = urlsplit(url).netloc == urlsplit(self.origin).netloc
        try:
            return await self.client.request(method, url, headers=self._headers() if same_host else None, **kwargs)
        except httpx.HTTPError as exc:
            raise AIError(f"Could not reach OpenRouter: {exc}") from exc

    async def _run(self, model: str, prompt: str, data_url: str, aspect_ratio: str) -> VideoResult:
        s = self.settings
        payload = video_payload(model, prompt, data_url, aspect_ratio, s.video_resolution, s.video_seconds)
        resp = await self._call("POST", f"{s.openrouter_base_url}/videos", json=payload)
        if resp.status_code in _TRY_NEXT:
            raise _ModelRefused(_error_message(resp))
        if resp.status_code >= 400:
            raise AIError(_error_message(resp))

        job = resp.json()
        deadline = time.monotonic() + s.video_timeout_seconds
        while job.get("status") not in TERMINAL:
            if time.monotonic() > deadline:
                raise AIError("The video took too long. Please try again.")
            await asyncio.sleep(self.poll_interval)
            poll = await self._call("GET", urljoin(self.origin, job["polling_url"]))
            if poll.status_code >= 400:
                raise AIError(_error_message(poll))
            job = poll.json()

        if job["status"] != "completed":
            # Failed jobs aren't billed, and are often a content refusal, so try the next model.
            raise _ModelRefused(job.get("error") or f"video job {job['status']}")

        url = (job.get("unsigned_urls") or [f"{s.openrouter_base_url}/videos/{job['id']}/content?index=0"])[0]
        clip = await self._call("GET", urljoin(self.origin, url), follow_redirects=True)
        if clip.status_code >= 400:
            raise AIError(f"Could not download the video ({clip.status_code}).")
        cost = (job.get("usage") or {}).get("cost")
        log.info("video from %s: %d bytes, cost %s", model, len(clip.content), cost)
        return VideoResult(clip.content, model, cost)
