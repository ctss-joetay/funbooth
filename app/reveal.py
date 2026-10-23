"""Before/after GIF: the original photo wipes across into the AI version, then loops."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageOps

from .printing import _font

WIDTH = 480
HOLD_BEFORE_MS = 900
WIPE_FRAMES, WIPE_MS = 12, 70
HOLD_AFTER_MS = 2200
FADE_FRAMES, FADE_MS = 4, 90


def _label(img: Image.Image, text: str, right: bool) -> Image.Image:
    img = img.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(max(14, img.width // 30), bold=True)
    box = draw.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    pad, margin = h // 2 + 2, img.width // 40
    x = img.width - margin - w - 2 * pad if right else margin
    y = img.height - margin - h - 2 * pad
    draw.rounded_rectangle((x, y, x + w + 2 * pad, y + h + 2 * pad), radius=h, fill=(0, 0, 0, 150))
    draw.text((x + pad, y + pad - box[1]), text, font=font, fill="white")
    return img


def make_reveal_gif(original: bytes, result: bytes, width: int = WIDTH) -> bytes:
    after = ImageOps.exif_transpose(Image.open(io.BytesIO(result))).convert("RGB")
    size = (width, round(width * after.height / after.width))
    after = ImageOps.fit(after, size, Image.LANCZOS)
    before = ImageOps.fit(ImageOps.exif_transpose(Image.open(io.BytesIO(original))).convert("RGB"), size, Image.LANCZOS)
    before, after = _label(before, "BEFORE", right=False), _label(after, "AFTER", right=True)

    frames, durations = [before], [HOLD_BEFORE_MS]
    for i in range(1, WIPE_FRAMES + 1):
        t = i / WIPE_FRAMES
        x = round(size[0] * (1 - (1 - t) ** 2))  # ease out
        frame = before.copy()
        frame.paste(after.crop((0, 0, x, size[1])), (0, 0))
        if i < WIPE_FRAMES:
            draw = ImageDraw.Draw(frame, "RGBA")
            draw.rectangle((x - 6, 0, x + 6, size[1]), fill=(255, 255, 255, 70))
            draw.rectangle((x - 2, 0, x + 2, size[1]), fill=(255, 255, 255, 255))
        frames.append(frame)
        durations.append(WIPE_MS)
    durations[-1] = HOLD_AFTER_MS
    for i in range(1, FADE_FRAMES + 1):
        frames.append(Image.blend(after, before, i / FADE_FRAMES))
        durations.append(FADE_MS)

    # One shared palette (from both pictures) lets the GIF store only what changes per frame.
    both = Image.new("RGB", (size[0] * 2, size[1]))
    both.paste(before, (0, 0))
    both.paste(after, (size[0], 0))
    palette = both.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    palette_frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    out = io.BytesIO()
    palette_frames[0].save(out, "GIF", save_all=True, append_images=palette_frames[1:], duration=durations, loop=0, disposal=1)
    return out.getvalue()
