"""Runtime settings, read once from environment variables."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("funbooth")

DEFAULT_MODEL = "bytedance-seed/seedream-5-0-flash"


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_base_url: str
    model: str
    # "images" = POST /images, "chat" = POST /chat/completions,
    # "auto" = try /images first and fall back to chat on a 4xx.
    api_mode: str
    resolution: str
    timeout_seconds: float
    booth_pin: str
    default_event_name: str
    data_dir: Path
    public_url: str

    @property
    def mock_ai(self) -> bool:
        """No API key means we fake the AI step so the booth can be tested for free."""
        return not self.openrouter_api_key


def _public_url() -> str:
    explicit = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain:
        return f"https://{railway_domain}"
    return ""  # fall back to the request's own base URL


def load_settings() -> Settings:
    pin = os.getenv("BOOTH_PIN", "").strip()
    if not pin:
        pin = f"{secrets.randbelow(10**6):06d}"
        log.warning("BOOTH_PIN is not set. Using a temporary PIN for this run: %s", pin)

    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip(),
        api_mode=os.getenv("OPENROUTER_API_MODE", "auto").strip().lower(),
        resolution=os.getenv("OPENROUTER_RESOLUTION", "2K").strip(),
        timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT", "120")),
        booth_pin=pin,
        default_event_name=os.getenv("EVENT_NAME", "Fun Booth").strip(),
        data_dir=Path(os.getenv("DATA_DIR", "./data")).resolve(),
        public_url=_public_url(),
    )
