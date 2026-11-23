#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обложки статей: графические, с мотивом под каждую тему.

Идея: цвет и рисунок кодируют рубрику, поэтому в ленте Дзена и на сайте
читатель узнаёт тему до чтения заголовка:

    Работа и доход    — синий,  столбики роста
    ИИ и инструменты  — фиолетовый, сеть узлов
    Дом и быт         — зелёный, окна дома
    Авто и путь       — оранжевый, дорога

Заголовок статьи на обложку не наносится: он есть рядом в карточке и в ленте.

    python scripts/make_cover.py --list      # только для статей без обложки
    python scripts/make_cover.py --all       # перерисовать все
"""

from __future__ import annotations

import hashlib
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
COVERS = ROOT / "static" / "covers"

SIZE = (1200, 630)

# палитра: (верхний цвет, нижний цвет, цвет мотива)
RUBRIC_STYLE = {
    "rabota-i-dohod": ((37, 99, 235), (9, 20, 46), (147, 197, 253)),
    "ii-instrumenty": ((124, 58, 237), (28, 17, 64), (196, 181, 253)),
    "dom-i-byt": ((5, 150, 105), (4, 47, 42), (167, 243, 208)),
    "karta-i-put": ((234, 88, 12), (59, 18, 4), (253, 186, 116)),
}
RUBRIC_TITLES = {
    "rabota-i-dohod": "Работа и доход",
    "ii-instrumenty": "ИИ и инструменты",
    "dom-i-byt": "Дом и быт",
    "karta-i-put": "Авто и путь",
}
DEFAULT_STYLE = ((26, 86, 219), (15, 23, 42), (191, 219, 254))

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


def gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, bottom)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    return img


def glow(size: tuple[int, int], color: tuple, rnd: random.Random) -> Image.Image:
    """Мягкое пятно света, чтобы фон не выглядел плоским."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = int(w * rnd.uniform(0.55, 0.95))
    cy = int(h * rnd.uniform(-0.1, 0.35))
    r = int(w * rnd.uniform(0.35, 0.55))
    for i in range(18, 0, -1):
        alpha = int(3 + (18 - i) * 0.9)
        rr = int(r * i / 18)
        d.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], fill=color + (alpha,))
    return layer


def motif_rabota(draw: ImageDraw.ImageDraw, w: int, h: int,
                 color: tuple, rnd: random.Random) -> None:
    """Столбики роста + восходящая линия."""
    base_y = int(h * 0.80)
    bars = 5
    bw = int(w * 0.045)
    gap = int(w * 0.022)
    total = bars * bw + (bars - 1) * gap
    x0 = int(w * 0.98 - total)
    points = []
    for i in range(bars):
        hgt = int(h * rnd.uniform(0.10, 0.34))
        x = x0 + i * (bw + gap)
        draw.rounded_rectangle([(x, base_y - hgt), (x + bw, base_y)], radius=8,
                               fill=color + (46,))
        points.append((x + bw // 2, base_y - hgt - 14))
    draw.line(points, fill=color + (120,), width=5, joint="curve")
    for px, py in points:
        draw.ellipse([(px - 7, py - 7), (px + 7, py + 7)], fill=color + (200,))


def motif_ii(draw: ImageDraw.ImageDraw, w: int, h: int,
             color: tuple, rnd: random.Random) -> None:
    """Сеть узлов: точки и связи между соседними."""
    nodes = []
    for _ in range(9):
        nodes.append((int(w * rnd.uniform(0.50, 0.96)), int(h * rnd.uniform(0.12, 0.80))))
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            dist = math.dist(a, b)
            if dist < w * 0.22:
                draw.line([a, b], fill=color + (38,), width=2)
    for i, (x, y) in enumerate(nodes):
        r = 15 if i % 4 == 0 else 8
        draw.ellipse([(x - r, y - r), (x + r, y + r)],
                     fill=color + ((150 if r > 10 else 110),))


def motif_dom(draw: ImageDraw.ImageDraw, w: int, h: int,
              color: tuple, rnd: random.Random) -> None:
    """Окна дома: сетка скруглённых квадратов и линия крыши."""
    cols, rows = 3, 2
    cell = int(w * 0.075)
    gap = int(w * 0.020)
    total_w = cols * cell + (cols - 1) * gap
    x0 = int(w * 0.97 - total_w)
    y0 = int(h * 0.34)
    for r in range(rows):
        for c in range(cols):
            x = x0 + c * (cell + gap)
            y = y0 + r * (cell + gap)
            draw.rounded_rectangle([(x, y), (x + cell, y + cell)], radius=10,
                                   fill=color + ((34 if (r + c) % 3 else 74),))
    # крыша
    roof_y = y0 - int(h * 0.06)
    draw.line([(x0 - gap, roof_y), (x0 + total_w + gap, roof_y)],
              fill=color + (120,), width=6)
    draw.line([(x0 - gap, roof_y), (x0 + total_w // 2, roof_y - int(h * 0.11))],
              fill=color + (120,), width=6)
    draw.line([(x0 + total_w + gap, roof_y), (x0 + total_w // 2, roof_y - int(h * 0.11))],
              fill=color + (120,), width=6)


def motif_karta(draw: ImageDraw.ImageDraw, w: int, h: int,
                color: tuple, rnd: random.Random) -> None:
    """Дорога: полоса с пунктиром уходит вдаль, слева — горизонт."""
    band_top, band_bot = h * 0.50, h * 0.86
    draw.polygon([(0, int(band_top)), (w, int(band_top - h * 0.12)),
                  (w, int(band_bot - h * 0.16)), (0, int(band_bot))],
                 fill=color + (26,))
    # пунктир по центру полосы
    steps = 8
    for i in range(steps):
        t0 = i / steps + 0.015
        t1 = t0 + 0.06
        mid0 = (band_top + band_bot) * 0.5 - h * 0.06 * t0
        mid1 = (band_top + band_bot) * 0.5 - h * 0.06 * t1
        draw.line([(int(w * t0), int(mid0)), (int(w * t1), int(mid1))],
                  fill=color + (140,), width=7)
    draw.line([(0, int(h * 0.50)), (w, int(h * 0.38))], fill=color + (60,), width=3)


MOTIFS = {
    "rabota-i-dohod": motif_rabota,
    "ii-instrumenty": motif_ii,
    "dom-i-byt": motif_dom,
    "karta-i-put": motif_karta,
}


def make(rubric: str, filename: str, seed: str = "") -> Path:
    top, bottom, accent = RUBRIC_STYLE.get(rubric, DEFAULT_STYLE)
    rnd = random.Random(int(hashlib.md5((seed or filename).encode("utf-8")).hexdigest()[:12], 16))

    img = gradient(SIZE, top, bottom).convert("RGBA")
    img = Image.alpha_composite(img, glow(SIZE, accent, rnd))

    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    motif = MOTIFS.get(rubric)
    if motif:
        motif(d, SIZE[0], SIZE[1], accent, rnd)
    img = Image.alpha_composite(img, overlay)

    d = ImageDraw.Draw(img)
    w, h = SIZE
    # плавное затемнение снизу под подпись рубрики
    shade = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ds = ImageDraw.Draw(shade)
    start = int(h * 0.42)
    for y in range(start, h):
        t = (y - start) / max(1, h - start)
        ds.line([(0, y), (w, y)], fill=(0, 0, 0, int(105 * t ** 1.35)))
    img = Image.alpha_composite(img, shade)

    d = ImageDraw.Draw(img)
    d.text((80, 62), BRAND, font=font(REG, 30), fill=(255, 255, 255, 200))
    title = RUBRIC_TITLES.get(rubric)
    if title:
        d.text((80, h - 176), title, font=font(BOLD, 74), fill=(255, 255, 255))

    COVERS.mkdir(parents=True, exist_ok=True)
    out = COVERS / filename
    img.convert("RGB").save(out, "JPEG", quality=88, optimize=True, progressive=True)
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
            if (COVERS / a.cover).exists() and not rebuild_all:
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
