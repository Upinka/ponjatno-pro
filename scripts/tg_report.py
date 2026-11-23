#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Отчёт о состоянии контент-проекта в Telegram.

Токен и chat_id берутся из переменных окружения TG_BOT_TOKEN / TG_CHAT_ID
или из файла .env в корне проекта.

Примеры:
    python scripts/tg_report.py --dry-run     # показать отчёт, не отправляя
    python scripts/tg_report.py               # отправить
    python scripts/tg_report.py --message "тест"   # своё сообщение
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MSK = timezone(timedelta(hours=3))


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("TG_BOT_TOKEN", "TG_CHAT_ID"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def collect() -> dict:
    sys.path.insert(0, str(ROOT))
    import build  # noqa: E402  — переиспользуем парсер статей

    cfg = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
    articles = build.load_articles()
    drafts = []
    for path in sorted((ROOT / "content").rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        if "status: draft" in raw:
            drafts.append(path)

    now = datetime.now(MSK)
    week_ago = now - timedelta(days=7)
    per_rubric: dict[str, int] = {}
    for a in articles:
        per_rubric[a.rubric] = per_rubric.get(a.rubric, 0) + 1

    return {
        "cfg": cfg,
        "total": len(articles),
        "per_rubric": per_rubric,
        "recent_week": [a for a in articles if a.date >= week_ago],
        "latest": articles[:3],
        "drafts": drafts,
        "feed_items": sum(1 for a in articles
                          if a.date >= now - timedelta(days=int(cfg["feed"]["window_days"]))),
    }


def build_message(data: dict) -> str:
    cfg = data["cfg"]
    rubrics = {r["slug"]: r["title"] for r in cfg["rubrics"]}
    today = datetime.now(MSK).strftime("%d.%m.%Y")

    lines = [
        "📊 <b>%s</b> — отчёт %s" % (cfg["site"]["title"], today),
        "",
        "Всего статей: <b>%d</b> · в ленте RSS: %d" % (data["total"], data["feed_items"]),
        "Черновиков: %d" % len(data["drafts"]),
        "",
        "<b>По направлениям</b>",
    ]
    for slug, title in rubrics.items():
        lines.append("• %s: %d" % (title, data["per_rubric"].get(slug, 0)))

    lines += ["", "<b>За последние 7 дней</b>: %d" % len(data["recent_week"])]
    for a in data["recent_week"][:5]:
        lines.append("• %s" % a.title)

    if data["latest"]:
        lines += ["", "<b>Последние материалы</b>"]
        for a in data["latest"]:
            lines.append("• %s (%s)" % (a.title, a.date.strftime("%d.%m")))

    if data["total"] < 10:
        lines += ["", "⚠️ Меньше 10 материалов: Дзен требует минимум 10 "
                      "при первой подаче RSS."]

    lines += ["", cfg["site"]["base_url"]]
    return "\n".join(lines)


def send(text: str, token: str, chat_id: str) -> None:
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit("Telegram ответил %s: %s" % (exc.code, detail))
    except urllib.error.URLError as exc:
        raise SystemExit("Не удалось связаться с Telegram: %s" % exc.reason)

    if not body.get("ok"):
        raise SystemExit("Telegram вернул ошибку: %s" % json.dumps(body, ensure_ascii=False))
    print("Отправлено в чат %s" % chat_id)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    if "--message" in args:
        idx = args.index("--message")
        text = args[idx + 1] if len(args) > idx + 1 else "ping"
    else:
        text = build_message(collect())

    if "--dry-run" in args:
        print(text)
        return

    env = load_env()
    token, chat_id = env.get("TG_BOT_TOKEN"), env.get("TG_CHAT_ID")
    if not token or not chat_id:
        print("Не заданы TG_BOT_TOKEN / TG_CHAT_ID.\n")
        print("Создайте .env рядом с build.py по образцу .env.example, либо задайте "
              "переменные окружения. Для предпросмотра используйте --dry-run.\n")
        print(text)
        sys.exit(2)

    send(text, token, chat_id)


if __name__ == "__main__":
    main()
