"""Photos on disk: DATA_DIR/photos/<id>/{original.jpg,result.jpg,meta.json}.

On Railway, mount a volume at DATA_DIR so photos survive redeploys.
"""

from __future__ import annotations

import io
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_SIDE = 2048


@dataclass
class PhotoRecord:
    id: str
    created_at: float
    theme_id: str
    custom_prompt: str
    orientation: str
    status: str = "processing"  # processing | done | error
    error: str = ""
    version: int = 0  # bumped on every (re)generation so browsers refetch

    def public(self) -> dict:
        v = self.version
        return {
            **asdict(self),
            "original_url": f"/media/{self.id}/original.jpg",
            "thumb_url": f"/media/{self.id}/thumb.jpg?v={v}-{self.status}",
            "result_url": f"/media/{self.id}/result.jpg?v={v}" if self.status == "done" else None,
            "print_url": f"/media/{self.id}/print.jpg?v={v}" if self.status == "done" else None,
            "share_path": f"/p/{self.id}",
            "qr_url": f"/qr/{self.id}.svg",
        }


def valid_id(photo_id: str) -> bool:
    return bool(_ID_RE.match(photo_id))


def normalize_jpeg(data: bytes, max_side: int = MAX_SIDE, quality: int = 90) -> bytes:
    """Decode any image Pillow understands, fix rotation, shrink, and re-encode as JPEG."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Unsupported or corrupt image") from exc
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality)
    return out.getvalue()


class PhotoStore:
    def __init__(self, root: Path):
        self.root = root / "photos"
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, photo_id: str) -> Path:
        if not valid_id(photo_id):
            raise KeyError(photo_id)
        return self.root / photo_id

    def path(self, photo_id: str, kind: str) -> Path:
        return self._dir(photo_id) / f"{kind}.jpg"

    def create(self, original_jpeg: bytes, theme_id: str, custom_prompt: str, orientation: str) -> PhotoRecord:
        rec = PhotoRecord(
            id=uuid.uuid4().hex,
            created_at=time.time(),
            theme_id=theme_id,
            custom_prompt=custom_prompt,
            orientation=orientation,
        )
        self._dir(rec.id).mkdir(parents=True)
        self.path(rec.id, "original").write_bytes(original_jpeg)
        self.save(rec)
        return rec

    def save(self, rec: PhotoRecord) -> None:
        meta = self._dir(rec.id) / "meta.json"
        tmp = meta.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(rec)))
        tmp.replace(meta)

    def get(self, photo_id: str) -> PhotoRecord | None:
        try:
            meta = self._dir(photo_id) / "meta.json"
            raw = json.loads(meta.read_text())
        except (KeyError, OSError, ValueError):
            return None
        known = {f.name for f in fields(PhotoRecord)}
        return PhotoRecord(**{k: v for k, v in raw.items() if k in known})

    def recent(self, limit: int = 40) -> list[PhotoRecord]:
        # A busy event is a few hundred photos; reading every meta.json is cheap enough.
        records = [self.get(d.name) for d in self.root.iterdir() if d.is_dir() and valid_id(d.name)]
        found = sorted((r for r in records if r), key=lambda r: r.created_at, reverse=True)
        return found[:limit]
