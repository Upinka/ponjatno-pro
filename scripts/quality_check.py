#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка качества статей: ищет типовые проблемы автогенерации.

    python scripts/quality_check.py                 # все статьи
    python scripts/quality_check.py --days 7        # только свежие
    python scripts/quality_check.py --fail-under 70 # код выхода 1, если есть статьи ниже порога

Отчёт пишется в reports/quality.md
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "quality.md"
MSK = datetime.now().astimezone().tzinfo

sys.path.insert(0, str(ROOT))
import build  # noqa: E402

# региональные и фактические артефакты: для российского канала это красный флаг
FOREIGN_MARKERS = [
    "тенге", "казахстан", "беларус", "гривн", "злот", "рупий", "лари", "kzt",
]
# признаки выдуманной арифметики: «за 500 ₽ приходило 620 ₽»
SUSPICIOUS_MONEY = [
    r"за\s*\d[\d\s]*₽[^.]{0,60}приходило",
    r"приходило\s*\d[\d\s]*₽",
    r"выгоднее\s+пополнять",
    r"комисси\w*\s+пополнения\s+от\s+\d+\s*%\s+до\s+\d+\s*%",
]
# допустимые границы объёма по типу материала
LENGTH_LIMITS = {
    "note": (400, 2200),
    "instruction": (2000, 8000),
    "article": (2000, 16000),
}
FILLER = [
    "в современном мире", "как мы знаем", "важно отметить", "стоит отметить",
    "в заключение", "данная статья", "в этой статье", "как известно",
    "не секрет, что", "в наше время", "играет важную роль",
]
UNSOURCED_CLAIM = ["учёные выяснили", "исследование показало", "доказано", "статистика говорит"]
META = ["данный материал", "в данном материале", "я как ии", "как нейросеть"]


def paragraphs(md: str) -> list[str]:
    chunks = re.split(r"\n\s*\n", md)
    return [c.strip() for c in chunks if c.strip()]


def check(article) -> tuple[int, list[tuple[str, str]]]:
    issues: list[tuple[str, str]] = []
    body = article.body_md
    text = re.sub(r"[#>*_`\[\]()!]", " ", body)
    low = body.lower()
    words = len(text.split())
    chars = len(body)
    score = 100

    def add(sev: str, msg: str, penalty: int) -> None:
        nonlocal score
        issues.append((sev, msg))
        score -= penalty

    # объём по типу материала
    low_limit, high_limit = LENGTH_LIMITS.get(article.kind, LENGTH_LIMITS["article"])
    if chars < low_limit:
        add("high", "коротко для формата %s: %d знаков (нужно %d+)"
            % (article.kind, chars, low_limit), 18)
    elif chars > high_limit:
        add("low", "длинно для формата %s: %d знаков" % (article.kind, chars), 4)

    # структура
    h2 = len(re.findall(r"^## ", body, re.M))
    if h2 < 3 and article.kind != "note":
        add("medium", "мало подзаголовков: %d" % h2, 8)

    # заголовок и описание
    if len(article.title) > 100:
        add("medium", "заголовок длиннее 100 знаков (%d)" % len(article.title), 6)
    if not (40 <= len(article.description) <= 220):
        add("medium", "описание не в диапазоне 40–220 знаков (%d)" % len(article.description), 6)
    if not article.tags:
        add("low", "нет тегов", 3)
    if not article.cover:
        add("medium", "нет обложки", 5)

    # региональные артефакты — и в тексте, и в описании
    for marker in FOREIGN_MARKERS:
        if marker in low or marker in article.description.lower():
            add("high", "чужой регион/валюта: «%s»" % marker, 15)
            break

    # выдуманная арифметика с деньгами
    for pattern in SUSPICIOUS_MONEY:
        if re.search(pattern, low):
            add("high", "подозрительные расчёты с деньгами: /%s/" % pattern[:40], 18)
            break

    # вода и клише
    filler_hits = [f for f in FILLER if f in low]
    if filler_hits:
        add("medium", "клише: " + ", ".join(filler_hits[:3]), 4 * len(filler_hits[:3]))

    # голые утверждения без источника
    claim_hits = [c for c in UNSOURCED_CLAIM if c in low]
    if claim_hits and "http" not in low:
        add("high", "утверждение без источника: " + ", ".join(claim_hits[:2]), 12)

    # мета-язык
    meta_hits = [m for m in META if m in low]
    if meta_hits:
        add("medium", "мета-язык: " + ", ".join(meta_hits), 6)

    # цифры без единиц
    if re.search(r"\d{3,}(?![ ]?(₽|руб|%|знак|тыс|млн|млрд|мин|час|дн|шт|года|год))", text):
        add("low", "числа без единиц измерения", 2)

    # повторяющиеся абзацы
    seen: dict[str, int] = {}
    for p in paragraphs(body):
        key = re.sub(r"\W+", "", p.lower())[:80]
        if len(key) > 40:
            seen[key] = seen.get(key, 0) + 1
    doubles = [k for k, v in seen.items() if v > 1]
    if doubles:
        add("medium", "повторяются абзацы: %d" % len(doubles), 8)

    # разметка
    if body.count("**") % 2:
        add("high", "незакрытые ** в тексте", 10)
    if re.search(r"\[[^\]]*\]\(\s*\)", body):
        add("medium", "ссылка с пустым адресом", 6)

    # источники для статей с цифрами
    if re.search(r"\d+\s?(₽|руб|%)", body) and "http" not in low and article.kind == "article":
        add("low", "цифры без ссылок на источники", 4)

    return max(0, score), issues


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    days = int(args[args.index("--days") + 1]) if "--days" in args else None
    fail_under = int(args[args.index("--fail-under") + 1]) if "--fail-under" in args else None

    articles = build.load_articles()
    if days:
        since = datetime.now(build.MSK) - timedelta(days=days)
        articles = [a for a in articles if a.date >= since]

    rows = []
    for a in articles:
        score, issues = check(a)
        rows.append((score, a, issues))
    rows.sort(key=lambda r: r[0])

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Проверка качества статей", "",
             "Дата: " + datetime.now().strftime("%d.%m.%Y %H:%M"), "",
             "| Оценка | Статья | Проблемы |", "|---|---|---|"]
    for score, a, issues in rows:
        short = "; ".join("%s: %s" % (sev, msg) for sev, msg in issues[:4]) or "—"
        lines.append("| %d | %s | %s |" % (score, a.title[:60], short))
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("проверено статей: %d" % len(rows))
    print("средняя оценка: %.1f" % (sum(r[0] for r in rows) / max(1, len(rows))))
    print()
    for score, a, issues in rows[:12]:
        print("%3d  %-58s %s" % (score, a.title[:58], a.slug))
        for sev, msg in issues[:5]:
            print("       [%s] %s" % (sev, msg))
    below = [r for r in rows if r[0] < (fail_under or 0)]
    print("\nотчёт: reports/quality.md")
    if fail_under and below:
        print("ниже порога %d: %d статей" % (fail_under, len(below)))
        sys.exit(1)


if __name__ == "__main__":
    main()
