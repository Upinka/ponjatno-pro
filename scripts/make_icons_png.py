#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рендер PNG-версий иконок из SVG.

Как работает: собирает HTML-сетку с инлайн-SVG, снимает её headless Chrome
на прозрачном фоне и нарезает на отдельные PNG в нескольких размерах.

    python scripts/make_icons_png.py

Результат: icons/png/<имя>-<размер>.png
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "icons"
OUT = ICONS / "png"

CELL = 512          # размер ячейки в рендере
ICON_BOX = 448      # размер иконки внутри ячейки
COLS = 5
SCALE = 2           # рендер в 2×, затем уменьшение — так края остаются чёткими
SIZES = (512, 192, 128, 96, 48, 32, 16)
COLOR = "#1f2937"   # чернильный цвет, читается на светлом фоне

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    found = shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome")
    if found:
        return found
    raise SystemExit("Не найден Chrome/Edge для рендера SVG")


def build_html(names: list[str]) -> str:
    cells = []
    for name in names:
        svg = (ICONS / (name + ".svg")).read_text(encoding="utf-8")
        # viewBox сохраняем, размер задаём стилем
        cells.append(
            '<div class="cell"><div class="icon" style="color:%s">%s</div></div>'
            % (COLOR, svg)
        )
    rows = (len(names) + COLS - 1) // COLS
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html,body { margin:0; padding:0; background:transparent; }
  .grid { display:grid; grid-template-columns: repeat(%d, %dpx); grid-auto-rows: %dpx; }
  .cell { display:flex; align-items:center; justify-content:center; }
  .icon { width:%dpx; height:%dpx; display:flex; }
  .icon svg { width:100%%; height:100%%; }
</style></head><body>
<div class="grid">%s</div>
</body></html>""" % (COLS, CELL, CELL, ICON_BOX, ICON_BOX, "".join(cells))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    names = sorted(p.stem for p in ICONS.glob("*.svg"))
    if not names:
        raise SystemExit("Нет SVG в icons/")

    chrome = find_chrome()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = (len(names) + COLS - 1) // COLS
    width, height = COLS * CELL * SCALE, rows * CELL * SCALE

    html_path = ICONS / "_render.html"
    html_path.write_text(build_html(names), encoding="utf-8")

    shot = ICONS / "_render.png"
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--default-background-color=00000000",
            "--force-device-scale-factor=%d" % SCALE,
            "--no-first-run", "--user-data-dir=" + profile,
            "--window-size=%d,%d" % (COLS * CELL, rows * CELL),
            "--screenshot=" + str(shot),
            html_path.as_uri(),
        ]
        subprocess.run(cmd, check=False, capture_output=True, timeout=120)

    if not shot.exists():
        raise SystemExit("Chrome не создал скриншот")

    sheet = Image.open(shot).convert("RGBA")
    cell_px = CELL * SCALE
    made = 0
    for index, name in enumerate(names):
        col, row = index % COLS, index // COLS
        box = (col * cell_px, row * cell_px, (col + 1) * cell_px, (row + 1) * cell_px)
        cell = sheet.crop(box)
        for size in SIZES:
            img = cell if size == cell_px else cell.resize((size, size), Image.LANCZOS)
            path = OUT / ("%s-%d.png" % (name, size))
            img.save(path, "PNG", optimize=True)
            made += 1
        print("готово:", name)

    shot.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)
    print("файлов PNG: %d (иконок %d × размеров %d)" % (made, len(names), len(SIZES)))
    print("папка:", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
