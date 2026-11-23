#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генерация айдентики канала: аватар (круглый кроп) и шапка.

    python scripts/make_brand.py

Результат в brand/:
    avatar.png      1000x1000  — аватар канала (Дзен обрезает в круг)
    avatar-alt.png  1000x1000  — второй вариант палитры
    header.png      1600x600   — обложка/шапка канала
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "brand"

BRAND = "Понятно про"
TAGLINE = "Заработок · ИИ · Дом · Авто"
DOMAIN = "ponjatno-pro.ru"

PALETTES = {
    "blue": ((26, 86, 219), (15, 23, 42)),
    "green": ((5, 150, 105), (6, 78, 59)),
    "violet": ((124, 58, 237), (49, 20, 90)),
    "ink": ((17, 24, 39), (2, 6, 23)),
}

BOLD = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
REG = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def gradient(size: tuple[int, int], palette: str, angle: str = "vertical") -> Image.Image:
    start, end = PALETTES[palette]
    w, h = size
    img = Image.new("RGB", size, end)
    draw = ImageDraw.Draw(img)
    if angle == "diagonal":
        for x in range(w):
            t = x / w
            color = tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))
            draw.line([(x, 0), (x, h)], fill=color)
    else:
        for y in range(h):
            t = y / h
            color = tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))
            draw.line([(0, y), (w, y)], fill=color)
    return img


def centered_text(draw, box, text, fnt, fill=(255, 255, 255)):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    w, h = right - left, bottom - top
    x = box[0] + (box[2] - box[0] - w) / 2 - left
    y = box[1] + (box[3] - box[1] - h) / 2 - top
    draw.text((x, y), text, font=fnt, fill=fill)


def make_avatar(palette: str, filename: str) -> Path:
    """Аватар: монограмма в центре, чтобы не обрезалась круглым кропом."""
    size = 1000
    img = gradient((size, size), palette, "diagonal")
    draw = ImageDraw.Draw(img)

    # безопасная зона круга — центральные ~64%
    safe = (size * 0.18, size * 0.18, size * 0.82, size * 0.82)
    centered_text(draw, safe, "ПП", font(BOLD, 380))

    # тонкая линия под монограммой как акцент
    y = int(size * 0.66)
    draw.line([(int(size * 0.32), y), (int(size * 0.68), y)], fill=(255, 255, 255), width=6)
    centered_text(draw, (safe[0], y + 24, safe[2], safe[3]), BRAND.upper(), font(REG, 52))

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    img.save(path, "PNG", optimize=True)
    return path


def make_header(palette: str) -> Path:
    w, h = 1600, 600
    img = gradient((w, h), palette, "diagonal")
    draw = ImageDraw.Draw(img)

    draw.text((110, 190), BRAND, font=font(BOLD, 118), fill=(255, 255, 255))
    draw.text((114, 330), TAGLINE, font=font(REG, 46), fill=(226, 232, 240))
    draw.line([(114, 420), (520, 420)], fill=(255, 255, 255), width=5)
    draw.text((114, 445), DOMAIN, font=font(REG, 34), fill=(203, 213, 225))

    # плашки рубрик справа — показывают, что канал мультитема
    chips = ["Работа и доход", "ИИ и инструменты", "Дом и быт", "Авто и путь"]
    chip_font = font(REG, 32)
    cw, ch, gap = 360, 64, 16
    x0 = w - 110 - cw
    y0 = (h - (len(chips) * ch + (len(chips) - 1) * gap)) // 2
    for i, label in enumerate(chips):
        cy = y0 + i * (ch + gap)
        draw.rounded_rectangle([(x0, cy), (x0 + cw, cy + ch)], radius=16,
                               outline=(255, 255, 255), width=2)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=chip_font)
        draw.text((x0 + (cw - (right - left)) / 2 - left,
                   cy + (ch - (bottom - top)) / 2 - top),
                  label, font=chip_font, fill=(255, 255, 255))

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "header.png"
    img.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("аватар:", make_avatar("blue", "avatar.png").relative_to(ROOT))
    print("аватар (вариант):", make_avatar("violet", "avatar-alt.png").relative_to(ROOT))
    print("шапка:", make_header("blue").relative_to(ROOT))


if __name__ == "__main__":
    main()
