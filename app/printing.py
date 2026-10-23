"""Builds the print-ready 4x6" image: themed frame, photo, event name, date and QR code."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .themes import Theme

DPI = 300
MARGIN = 40

# Print layouts at 300 dpi. The photo box is close to the aspect ratio we ask the AI for,
# so the final crop is tiny.
LAYOUTS = {
    "landscape": {"size": (1800, 1200), "footer": 190, "qr": 160, "ai_ratio": "16:9"},
    "portrait": {"size": (1200, 1800), "footer": 250, "qr": 190, "ai_ratio": "3:4"},
}

# Bundled so prints look the same on every machine (DejaVu, Bitstream Vera licence).
FONT_DIR = Path(__file__).resolve().parent / "fonts"
_FONTS = {True: FONT_DIR / "DejaVuSans-Bold.ttf", False: FONT_DIR / "DejaVuSans.ttf"}


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(_FONTS[bold]), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int, bold: bool) -> ImageFont.FreeTypeFont:
    size = start
    while size > 18:
        font = _font(size, bold)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return _font(size, bold)


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def layout_for(orientation: str) -> dict:
    return LAYOUTS.get(orientation, LAYOUTS["landscape"])


def qr_image(url: str, size: int, dark: str, light: str) -> Image.Image:
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=2, dark=dark, light=light)
    buf.seek(0)
    return Image.open(buf).convert("RGB").resize((size, size), Image.NEAREST)


def compose_print(
    photo_bytes: bytes,
    theme: Theme,
    event_name: str,
    date_text: str,
    orientation: str = "landscape",
    qr_url: str | None = None,
) -> bytes:
    layout = layout_for(orientation)
    width, height = layout["size"]
    footer = layout["footer"]
    frame, accent, ink = _hex(theme.frame), _hex(theme.accent), _hex(theme.ink)

    canvas = Image.new("RGB", (width, height), frame)
    draw = ImageDraw.Draw(canvas)

    # Photo, cover-cropped into its box with an accent outline.
    box_w = width - 2 * MARGIN
    box_h = height - MARGIN - footer
    photo = Image.open(io.BytesIO(photo_bytes))
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    photo = ImageOps.fit(photo, (box_w, box_h), Image.LANCZOS, centering=(0.5, 0.4))
    canvas.paste(photo, (MARGIN, MARGIN))
    draw.rectangle(
        (MARGIN - 6, MARGIN - 6, MARGIN + box_w + 5, MARGIN + box_h + 5), outline=accent, width=6
    )

    # Footer: event name + theme/date on the left, QR on the right.
    footer_top = MARGIN + box_h
    qr_size = layout["qr"] if qr_url else 0
    text_right = width - MARGIN - (qr_size + 24 if qr_url else 0)
    text_w = text_right - MARGIN

    title = event_name.strip() or "Fun Booth"
    subtitle = f"{theme.name}  ·  {date_text}" if theme.id != "custom" else date_text
    title_font = _fit_font(draw, title, text_w, 72 if orientation == "landscape" else 80, bold=True)
    sub_font = _fit_font(draw, subtitle, text_w, 36 if orientation == "landscape" else 40, bold=False)

    title_box = draw.textbbox((0, 0), title, font=title_font)
    sub_box = draw.textbbox((0, 0), subtitle, font=sub_font)
    title_h = title_box[3] - title_box[1]
    sub_h = sub_box[3] - sub_box[1]
    gap = 18
    block_h = title_h + gap + sub_h
    y = footer_top + (footer - block_h) // 2
    draw.text((MARGIN, y - title_box[1]), title, font=title_font, fill=ink)
    draw.text((MARGIN, y + title_h + gap - sub_box[1]), subtitle, font=sub_font, fill=accent)

    if qr_url:
        # Always dark-on-white: inverted QR codes don't scan on every phone.
        qr = qr_image(qr_url, qr_size, dark="#111111", light="#ffffff")
        qr_x = width - MARGIN - qr_size
        qr_y = footer_top + (footer - qr_size) // 2
        canvas.paste(qr, (qr_x, qr_y))

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=93, dpi=(DPI, DPI))
    return out.getvalue()
