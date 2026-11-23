#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Готовит тексты статей для ручной публикации в редакторе Дзена.

    python scripts/make_manual.py                      # статьи с feed_exclude: true
    python scripts/make_manual.py --slug slug1 slug2   # конкретные статьи
    python scripts/make_manual.py --all                # все статьи

Результат: папка dzen-manual/, по файлу на статью + список для публикации.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dzen-manual"
COVERS = ROOT / "static" / "covers"

sys.path.insert(0, str(ROOT))
import build  # noqa: E402


def plain_text(md: str) -> str:
    """Markdown статьи -> текст, который нормально вставляется в редактор Дзена."""
    lines = []
    for raw in md.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            lines.append("")
            continue

        if stripped.startswith("### "):
            lines.append("")
            lines.append(stripped[4:])
            lines.append("")
            continue

        if stripped.startswith("## "):
            lines.append("")
            lines.append(stripped[3:])
            lines.append("")
            continue

        if re.match(r"^[-*] ", stripped):
            lines.append("— " + stripped[2:])
            continue

        if re.match(r"^\d+\. ", stripped):
            lines.append(re.sub(r"^(\d+)\. ", r"\1. ", stripped))
            continue

        if stripped.startswith("> "):
            lines.append("«" + stripped[2:] + "»")
            continue

        lines.append(stripped)

    text = "\n".join(lines)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    out_dir = Path(args[args.index("--out") + 1]) if "--out" in args else OUT
    articles = build.load_articles()

    if "--slug" in args:
        wanted = args[args.index("--slug") + 1:]
        selected = [a for a in articles if a.slug in wanted]
    elif "--all" in args:
        selected = articles
    else:
        selected = [a for a in articles if a.feed_exclude]

    if not selected:
        print("Нечего готовить: нет статей с feed_exclude: true "
              "(добавьте флаг в front matter или укажите --slug)")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    index_lines = ["# Публикация в Дзене — очередь", ""]

    for i, a in enumerate(sorted(selected, key=lambda x: x.date), 1):
        cover_path = COVERS / a.cover if a.cover else None
        cover_note = (str(cover_path.relative_to(ROOT)) if cover_path and cover_path.exists()
                      else "обложки нет — сгенерируйте: python scripts/make_cover.py --list")

        doc = [
            "# " + a.title,
            "",
            "**Рубрика:** " + a.rubric,
            "**Обложка:** `" + cover_note + "`",
            "**Теги:** " + (", ".join(a.tags) if a.tags else "—"),
            "**Подзаголовок (в поле «О чём статья»):** " + (a.description or "—"),
            "",
            "---",
            "",
            "## Текст для вставки в редактор",
            "",
            plain_text(a.body_md),
            "",
        ]

        name = "%02d-%s.md" % (i, a.slug)
        (out_dir / name).write_text("\n".join(doc), encoding="utf-8")
        index_lines.append("%d. **%s** — `%s`" % (i, a.title, name))
        print("готово: %s/%s" % (out_dir.name, name))

    index_name = "00-очередь.md"
    (out_dir / index_name).write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print("индекс: %s/%s" % (out_dir.name, index_name))


if __name__ == "__main__":
    main()
