#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обложки статей: графические, без текста заголовка.

Зачем без заголовка: обложка стоит и в карточке сайта, и в ленте Дзена.
Дублировать заголовок картинкой плохо — заголовок уже есть рядом.

    python scripts/make_cover.py --list      # для всех статей без обложки
    python scripts/make_cover.py --all       # перерисовать все обложки
    python scripts/make_cover.py "Рубрика" имя.jpg

Зависимости: Pillow.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
COVERS = ROOT / "static" / "covers"

SIZE = (1200, 630)

# палитра по рубрике: (начало градиента, конец градиента)
RUBRIC_PALETTES = {
    "rabota-i-dohod": ((37, 99, 235), (15, 23, 42)),
    "ii-instrumenty": ((124, 58, 237), (30, 27, 75)),
    "dom-i-byt": ((5, 150, 105), (6, 78, 59)),
    "karta-i-put": ((234, 88, 12), (69, 26, 3)),
}
RUBRIC_TITLES = {
    "rabota-i-dohod": "Работа и доход",
    "ii-instrumenty": "ИИ и инструменты",
    "dom-i-byt": "Дом и быт",
    "karta-i-put": "Авто и путь",
}
DEFAULT_PALETTE = ((26, 86, 219), (15, 23, 42))

BOLD = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
REG = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

BRAND = "ПОНЯТНО ПРО"


def font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def gradient(size: tuple[int, int], palette: tuple) -> Image.Image:
    start, end = palette
    w, h = size
    img = Image.new("RGB", size, end)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        color = tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    return img


def decorate(img: Image.Image, seed: str = "") -> None:
    """Полупрозрачные круги и линия. Сдвиг зависит от slug — карточки не близнецы."""
    import hashlib

    w, h = img.size
    dg = hashlib.md5(seed.encode("utf-8")).digest()
    dx = (dg[0] / 255.0 - 0.5) * 0.18
    dy = (dg[1] / 255.0 - 0.5) * 0.12

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse([(w * (0.58 + dx), -h * 0.35), (w * (1.04 + dx), h * 0.70)], fill=(255, 255, 255, 18))
    d.ellipse([(w * (0.76 + dy), h * (0.26 + dx)), (w * 1.04, h * 1.06)], fill=(255, 255, 255, 14))
    d.ellipse([(w * (0.04 + dy), h * (0.58 + dx)), (w * (0.22 + dy), h * 0.94)], fill=(255, 255, 255, 12))
    d.line([(0, h * (0.60 + dy)), (w, h * (0.60 + dy))], fill=(255, 255, 255, 22), width=2)
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def make(rubric: str, filename: str, seed: str = "") -> Path:
    palette = RUBRIC_PALETTES.get(rubric, DEFAULT_PALETTE)
    img = gradient(SIZE, palette)
    decorate(img, seed or filename)
    draw = ImageDraw.Draw(img)

    w, h = SIZE
    draw.text((80, 62), BRAND, font=font(REG, 30), fill=(255, 255, 255, 200))

    title = RUBRIC_TITLES.get(rubric)
    if title:
        draw.text((80, h - 190), title, font=font(BOLD, 76), fill=(255, 255, 255))

    COVERS.mkdir(parents=True, exist_ok=True)
    out = COVERS / filename
    img.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sys.path.insert(0, str(ROOT))
    import build  # noqa: E402

    args = sys.argv[1:]
    if "--all" in args or "--list" in args:
        rebuild_all = "--all" in args
        articles = build.load_articles()
        made = 0
        for a in articles:
            if not a.cover:
                continue
            exists = (COVERS / a.cover).exists()
            if exists and not rebuild_all:
                continue
            make(a.rubric, a.cover, a.slug)
            print("обложка:", "static/covers/" + a.cover)
            made += 1
        print("готово, обновлено: %d" % made)
        return

    if len(args) < 2:
        print(__doc__)
        return
    print("обложка:", make(args[0], args[1]).relative_to(ROOT))


if __name__ == "__main__":
    main()
