"""Generate the built-in theme samples for the guest carousel with the real AI model.

    OPENROUTER_API_KEY=sk-or-... python scripts/make_samples.py
    OPENROUTER_API_KEY=sk-or-... python scripts/make_samples.py --photo team.jpg

Without --photo, the model first creates a demo photo of fictional guests and then restyles
that same group in every theme, so the carousel shows one group transformed each time.
Results go to static/samples/<theme id>.jpg, which the app serves as default samples
(samples made in the operator's settings still take priority).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai import AIError, ImageAI  # noqa: E402
from app.booth import SAMPLE_SIZE  # noqa: E402
from app.config import STATIC_DIR, load_settings  # noqa: E402
from app.printing import layout_for  # noqa: E402
from app.storage import normalize_jpeg  # noqa: E402
from app.themes import THEMES, build_prompt  # noqa: E402

DEMO_GROUP = (
    "A candid, photorealistic photo booth picture of four smiling friends in their 20s to 40s "
    "of different ethnicities, two women and two men, standing close together and facing the "
    "camera, waist-up, smart casual party clothes, plain light grey studio backdrop, soft even "
    "lighting, sharp focus. Fictional people."
)
MAX_PARALLEL = 3


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--photo", type=Path, help="restyle this photo instead of an AI-made demo group")
    parser.add_argument("--orientation", choices=["landscape", "portrait"], default="landscape")
    parser.add_argument("--themes", nargs="*", help="theme ids to make (default: all)")
    parser.add_argument("--out", type=Path, default=STATIC_DIR / "samples")
    args = parser.parse_args()

    settings = load_settings()
    if settings.mock_ai:
        print("Set OPENROUTER_API_KEY first; without it there is only the mock AI.", file=sys.stderr)
        return 1
    ai = ImageAI(settings)
    ratio = layout_for(args.orientation)["ai_ratio"]
    themes = [t for t in THEMES if not args.themes or t.id in args.themes]
    args.out.mkdir(parents=True, exist_ok=True)

    try:
        if args.photo:
            base = normalize_jpeg(args.photo.read_bytes())
        else:
            print(f"Creating a demo photo with {settings.model}…")
            base = normalize_jpeg(await ai.create(DEMO_GROUP, ratio))
        (args.out / "_original.jpg").write_bytes(normalize_jpeg(base, SAMPLE_SIZE, 88))

        slots = asyncio.Semaphore(MAX_PARALLEL)

        async def one(theme) -> bool:
            async with slots:
                started = time.monotonic()
                try:
                    raw = await ai.transform(base, build_prompt(theme), ratio)
                except AIError as exc:
                    print(f"  ✗ {theme.id}: {exc}")
                    return False
            (args.out / f"{theme.id}.jpg").write_bytes(normalize_jpeg(raw, SAMPLE_SIZE, 88))
            print(f"  ✓ {theme.id} ({time.monotonic() - started:.0f}s)")
            return True

        print(f"Restyling into {len(themes)} themes…")
        results = await asyncio.gather(*(one(t) for t in themes))
    except AIError as exc:
        print(f"OpenRouter error: {exc}", file=sys.stderr)
        return 1
    finally:
        await ai.aclose()

    print(f"Done: {sum(results)}/{len(themes)} samples in {args.out}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
