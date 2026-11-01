"""Image helpers (placeholders, covers)."""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def placeholder_image(out: Path, width: int, height: int, text: str, seed: int) -> None:
    rnd = random.Random(seed)
    c1 = tuple(rnd.randint(30, 120) for _ in range(3))
    c2 = tuple(rnd.randint(120, 230) for _ in range(3))
    img = Image.new("RGB", (width, height))
    px = img.load()
    for y in range(height):
        t = y / max(1, height - 1)
        col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        for x in range(width):
            px[x, y] = col
    draw = ImageDraw.Draw(img)
    for _ in range(12):  # abstract "dunes"
        x0, y0 = rnd.randint(-width // 2, width), rnd.randint(height // 3, height)
        r = rnd.randint(width // 4, width)
        shade = tuple(max(0, c - rnd.randint(10, 60)) for c in c2)
        draw.ellipse([x0, y0, x0 + r, y0 + r // 2], fill=shade)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((40, 40), text[:120], fill=(255, 255, 255), font=font, spacing=6)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def to_cover_jpeg(src: Path, out: Path, width: int, height: int) -> None:
    img = Image.open(src).convert("RGB")
    scale = max(width / img.width, height / img.height)
    img = img.resize((int(img.width * scale + 0.5), int(img.height * scale + 0.5)), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    img = img.crop((left, top, left + width, top + height))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=92, icc_profile=None)
