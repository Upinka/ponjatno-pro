#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Комиксы-полоски к статьям: три панели с шагами.

Панели берутся из подзаголовков статьи (или из нумерованных пунктов, если
подзаголовков мало). Формат 1200×630, подходит и для Дзена, и для соцсетей.

    python scripts/make_comic.py --slug <slug> [--slug <slug2> ...]
    python scripts/make_comic.py --feed-excluded     # для всех статей с feed_exclude

Результат: dzen-manual/comics/<slug>.jpg
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dzen-manual" / "comics"

sys.path.insert(0, str(ROOT))
import build  # noqa: E402

W, H = 1200, 630
PAPER = (247, 245, 241)
INK = (17, 24, 39)
MUTED = (107, 114, 128)
LINE = (226, 226, 220)

RUBRIC_COLOR = {
    "rabota-i-dohod": (37, 99, 235),
    "ii-instrumenty": (124, 58, 237),
    "dom-i-byt": (5, 150, 105),
    "karta-i-put": (234, 88, 12),
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


def wrap(text: str, width_chars: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if len(probe) <= width_chars:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def panels_of(article) -> list[tuple[str, str]]:
    """Три пары (заголовок, пояснение) из подзаголовков статьи."""
    md = article.body_md
    lines = md.splitlines()
    pairs: list[tuple[str, str]] = []

    def clean(text: str) -> str:
        text = re.sub(r"\*\*|__|\*", "", text)
        return re.sub(r"^\d+\.\s*", "", text.strip())

    for i, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        title = clean(line[3:])[:64]
        block: list[str] = []
        for follow in lines[i + 1:]:
            if follow.startswith("#"):
                break
            if not follow.strip():
                if block:
                    break
                continue
            block.append(follow.strip())
            if len(block) >= 6:
                break

        snippet = ""
        if block and all(b[:2] in ("- ", "* ") for b in block):
            # список: берём первые два пункта без маркеров
            items_txt = [clean(b[2:]) for b in block[:2]]
            snippet = "; ".join(items_txt)
        elif block:
            snippet = clean(" ".join(block))

        parts = re.split(r"(?<=[.!?])\s+", snippet, maxsplit=1)
        snippet = parts[0][:110] if parts else ""
        pairs.append((title, snippet))
        if len(pairs) == 3:
            break

    if len(pairs) < 3:
        for item in re.findall(r"^\d+\.\s+(.+)$", md, re.M):
            text = clean(item)
            parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
            pairs.append((parts[0][:64], parts[1][:110] if len(parts) > 1 else ""))
            if len(pairs) == 3:
                break

    while len(pairs) < 3:
        pairs.append((["Что проверить", "Как сделать", "Чего избегать"][len(pairs)], ""))
    return pairs[:3]


def make(article, filename: str) -> Path:
    color = RUBRIC_COLOR.get(article.rubric, (37, 99, 235))
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # шапка
    d.text((40, 34), "ПОНЯТНО ПРО", font=font(REG, 20), fill=MUTED)
    title_lines = wrap(article.title, 46)[:2]
    y = 66
    for line in title_lines:
        d.text((40, y), line, font=font(BOLD, 34), fill=INK)
        y += 42
    d.line([(40, y + 8), (W - 40, y + 8)], fill=LINE, width=2)

    # три панели
    panel_w, panel_h = 352, 330
    gap = 22
    x0 = 40
    y0 = y + 34
    for idx, (title, snippet) in enumerate(panels_of(article), start=1):
        x = x0 + (idx - 1) * (panel_w + gap)
        d.rounded_rectangle([(x, y0), (x + panel_w, y0 + panel_h)], radius=18,
                            fill=(255, 255, 255), outline=LINE, width=2)
        # цветная плашка с номером
        d.rounded_rectangle([(x, y0), (x + panel_w, y0 + 84)], radius=18, fill=color)
        d.rectangle([(x, y0 + 60), (x + panel_w, y0 + 84)], fill=color)
        d.text((x + 26, y0 + 16), str(idx), font=font(BOLD, 42), fill=(255, 255, 255))

        # заголовок панели
        ty = y0 + 110
        for line in wrap(title, 24)[:3]:
            d.text((x + 24, ty), line, font=font(BOLD, 21), fill=INK)
            ty += 28
        # пояснение
        ty += 8
        for line in wrap(snippet, 30)[:5]:
            d.text((x + 24, ty), line, font=font(REG, 18), fill=MUTED)
            ty += 24

    # подпись
    d.text((40, H - 44), "ponjatno-pro.ru", font=font(REG, 20), fill=MUTED)
    d.text((W - 40 - 150, H - 44), "#" + article.rubric, font=font(REG, 18), fill=MUTED)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    img.save(path, "JPEG", quality=88, optimize=True, progressive=True)
    return path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    articles = build.load_articles()

    if "--slug" in args:
        wanted = args[args.index("--slug") + 1:]
        selected = [a for a in articles if a.slug in wanted]
    elif "--feed-excluded" in args:
        selected = [a for a in articles if a.feed_exclude]
    else:
        selected = articles

    if not selected:
        print("Нечего рисовать: проверьте --slug")
        return

    for a in selected:
        path = make(a, a.slug + ".jpg")
        print("комикс:", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
