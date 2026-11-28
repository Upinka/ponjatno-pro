#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Готовит пакет для ручной публикации материалов, которых нет в Дзене.

    python scripts/prepare_batch3.py

Что делает:
  1. считает статьи, которых нет в списке уже опубликованных в Дзене;
  2. ставит им feed_exclude (чтобы лента не создала дубли);
  3. раскладывает тексты, обложки и план по дням в dzen-manual/batch3/.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
COVERS = ROOT / "static" / "covers"
OUT = ROOT / "dzen-manual" / "batch3"

# то, что уже видно в Студии Дзена
PUBLISHED = {
    "gta-6-prodazhi-rekord", "gta-6-metacritic-99", "gta-6-pervyj-patch",
    "gde-nejroset-vret", "skolko-stoit-chas-raboty", "istoria-chit-kodov-gta",
    "gta-6-vyshla", "podgotovka-avto-k-zime-checklist",
    "porjadok-v-dokumentah-za-vyhodnye", "7-bytovyh-zadach-nejroset",
    "proverit-ideyu-podrabotki-za-vecher", "kak-nazvat-cenu-za-uslugu",
}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sys.path.insert(0, str(ROOT))
    import build  # noqa: E402

    articles = build.load_articles()
    by_slug = {a.slug: a for a in articles}
    missing = [a for a in articles if a.slug not in PUBLISHED]

    # 1. исключаем из ленты
    marked = 0
    for a in missing:
        path = a.source
        text = path.read_text(encoding="utf-8")
        if "feed_exclude" not in text:
            text = text.replace("status: published", "status: published\nfeed_exclude: true")
            path.write_text(text, encoding="utf-8")
            marked += 1
    print("помечено вне RSS:", marked)

    # 2. тексты и обложки
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "covers").mkdir(exist_ok=True)
    slugs = [a.slug for a in sorted(missing, key=lambda x: x.date)]

    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_manual.py"),
                    "--slug", *slugs, "--out", str(OUT)], cwd=ROOT, check=False)

    for a in missing:
        src = COVERS / a.cover if a.cover else None
        if src and src.exists():
            shutil.copy2(src, OUT / "covers" / a.cover)

    # 3. план по дням
    ordered = sorted(missing, key=lambda x: -x.date.timestamp())
    plan = ["# Партия 3 — публикация вручную", "",
            "Эти материалы не дошли до Дзена через RSS: импорт остановился около 25 ноября.",
            "Все они **исключены из ленты** (`feed_exclude`), поэтому дублей не будет.", "",
            "## Порядок: 5 материалов в день", ""]
    per_day = 5
    days = ["День 1", "День 2", "День 3", "День 4", "День 5", "День 6", "День 7"]
    for d, day in enumerate(days):
        chunk = ordered[d * per_day:(d + 1) * per_day]
        if not chunk:
            break
        plan.append("### " + day)
        for a in chunk:
            plan.append("- **%s** — `%02d-%s.md`, обложка `covers/%s`"
                        % (a.title, ordered.index(a) + 1, a.slug, a.cover))
        plan.append("")
    plan += [
        "## Как публиковать", "",
        "1. Студия → **Создать** → **Статья**.",
        "2. Заголовок — первая строка файла.",
        "3. Текст — блок «Текст для вставки в редактор»; строки-подзаголовки оформите стилем H2.",
        "4. Обложка — из папки `covers/`.",
        "5. Теги и «О чём статья» — из шапки файла.",
        "", "## Важно", "",
        "Материалов 34 — за один день их публиковать не нужно: Дзен плохо реагирует на массовую заливку.",
        "5 в день — это неделя спокойного темпа, и как раз за это время станет понятно, оживёт ли импорт по RSS.",
    ]
    (OUT / "ПЛАН.md").write_text("\n".join(plan) + "\n", encoding="utf-8")
    print("готово:", OUT.relative_to(ROOT), "| файлов:", len(list(OUT.glob('*.md'))))


if __name__ == "__main__":
    main()
