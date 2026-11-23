#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор обложек для статей (JPEG, 1200x630 — больше минимума Дзена в 700 px).

Использование:
    python scripts/make_cover.py "Заголовок статьи" rabota-proverka.jpg
    python scripts/make_cover.py --list          # сделать обложки для всех статей без cover

Требуется Pillow (входит в комплект зависимостей DSH). Если его нет:
    pip install Pillow
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERS = ROOT / "static" / "covers"
CONFIG = ROOT / "site.config.json"

SIZE = (1200, 630)
PALETTES = [
    ((26, 86, 219), (17, 24, 39)),
    ((5, 150, 105), (6, 78, 59)),
    ((180, 83, 9), (69, 26, 3)),
    ((124, 58, 237), (49, 20, 90)),
]


def wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if len(probe) <= width:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make(title: str, filename: str, palette_index: int = 0, brand: str = "Понятно про") -> Path:
    from PIL import Image, ImageDraw, ImageFont

    start, end = PALETTES[palette_index % len(PALETTES)]
    img = Image.new("RGB", SIZE, end)
    draw = ImageDraw.Draw(img)

    # диагональный градиент
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        color = tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))
        draw.line([(0, y), (SIZE[0], y)], fill=color)

    font_paths = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    small_paths = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def load(paths, size):
        for p in paths:
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        return ImageFont.load_default()

    title_font = load(font_paths, 64)
    brand_font = load(small_paths, 30)

    lines = wrap(title, 22)[:4]
    line_h = 78
    total = line_h * len(lines)
    y = (SIZE[1] - total) // 2 - 10
    for line in lines:
        draw.text((80, y), line, font=title_font, fill=(255, 255, 255))
        y += line_h

    draw.text((80, 60), brand.upper(), font=brand_font, fill=(226, 232, 240))
    draw.line([(80, SIZE[1] - 90), (SIZE[0] - 80, SIZE[1] - 90)], fill=(255, 255, 255), width=3)

    COVERS.mkdir(parents=True, exist_ok=True)
    out = COVERS / filename
    img.save(out, "JPEG", quality=88, optimize=True)
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if "--list" in sys.argv:
        sys.path.insert(0, str(ROOT))
        import build  # noqa: E402  (локальный модуль сборки)

        arts = build.load_articles()
        made = 0
        for i, a in enumerate(arts):
            if a.cover and (COVERS / a.cover).exists():
                continue
            name = a.cover or (a.slug + ".jpg")
            out = make(a.title, name, i)
            print("обложка: %s" % out.relative_to(ROOT))
            made += 1
        if not made:
            print("Все статьи уже с обложками.")
        return

    if len(sys.argv) < 3:
        print(__doc__)
        return
    title, filename = sys.argv[1], sys.argv[2]
    brand = json.loads(CONFIG.read_text(encoding="utf-8"))["site"]["title"] if CONFIG.exists() else "Понятно про"
    print("обложка: %s" % make(title, filename, 0, brand).relative_to(ROOT))


if __name__ == "__main__":
    main()
