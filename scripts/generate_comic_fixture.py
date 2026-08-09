"""Generate tests/fixtures/comic_2x2.png — 4-panel page with gutters for detector QA."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate_comic_2x2(out: Path | None = None) -> Path:
    root = Path(__file__).resolve().parent.parent
    out = out or root / "tests" / "fixtures" / "comic_2x2.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    w, h = 800, 1100
    gutter = 12
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)

    cols = [(0, w // 2 - gutter // 2), (w // 2 + gutter // 2, w)]
    rows = [(0, h // 2 - gutter // 2), (h // 2 + gutter // 2, h)]

    dialogues = [
        '"Panel one!"',
        '"What happened?"',
        "BOOM",
        '"We need answers."',
    ]
    idx = 0
    for ri, (y0, y1) in enumerate(rows):
        for ci, (x0, x1) in enumerate(cols):
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline="black", width=5)
            tx, ty = x0 + 24, y0 + 24
            draw.rounded_rectangle([tx, ty, tx + 200, ty + 56], radius=8, outline="black", width=2)
            try:
                font = ImageFont.truetype("arial.ttf", 18)
            except OSError:
                font = ImageFont.load_default()
            draw.text((tx + 10, ty + 14), dialogues[idx % len(dialogues)], fill="black", font=font)
            idx += 1

    for x in range(w):
        draw.line([(x, h // 2 - gutter // 2), (x, h // 2 + gutter // 2)], fill="white", width=gutter)
    for y in range(h):
        draw.line([(w // 2 - gutter // 2, y), (w // 2 + gutter // 2, y)], fill="white", width=gutter)

    img.save(out)
    return out


if __name__ == "__main__":
    path = generate_comic_2x2()
    print(f"Wrote {path}")