#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ интереса к статьям по данным Яндекс.Метрики.

    python scripts/analytics.py              # отчёт за 7 дней
    python scripts/analytics.py --days 30
    python scripts/analytics.py --json       # машинный вывод для агента

Нужен OAuth-токен Метрики в .env:  METRIKA_TOKEN=...
Как получить токен:
  1. https://oauth.yandex.ru/ — создайте приложение «для доступа к API Метрики»
  2. права: metrika:read
  3. получите токен по ссылке вида
     https://oauth.yandex.ru/authorize?response_type=token&client_id=<ID клиента>
  4. скопируйте access_token из адресной строки в .env

Без токена скрипт объяснит, что делать, и завершится без ошибки.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "site.config.json"
ENV_FILE = ROOT / ".env"
REPORT = ROOT / "analytics" / "report.json"

API = "https://api-metrika.yandex.net/stat/v1/data"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def counter_id() -> str | None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    value = cfg.get("analytics", {}).get("yandex_metrika_id")
    return str(value) if value else None


def fetch(token: str, cid: str, days: int) -> dict:
    date2 = date.today()
    date1 = date2 - timedelta(days=days)
    params = {
        "id": cid,
        "metrics": "ym:s:pageviews,ym:s:users,ym:s:bounceRate,ym:s:avgVisitDurationSeconds",
        "dimensions": "ym:s:startURLPath",
        "date1": date1.isoformat(),
        "date2": date2.isoformat(),
        "limit": "100",
        "sort": "-ym:s:pageviews",
        "filters": "ym:s:isRobot=='No'",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": "OAuth " + token,
        "User-Agent": "dsh-analytics",
    })
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def rubric_of(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    return parts[0] if parts else "index"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    days = int(args[args.index("--days") + 1]) if "--days" in args else 7
    as_json = "--json" in args

    env = load_env()
    token = env.get("METRIKA_TOKEN")
    cid = counter_id()

    if not cid:
        print("В site.config.json не задан analytics.yandex_metrika_id")
        sys.exit(2)
    if not token:
        print("Нет токена Метрики в .env (METRIKA_TOKEN).")
        print("Счётчик %s уже стоит на сайте и собирает данные." % cid)
        print("Чтобы я мог их читать автоматически, нужен OAuth-токен:")
        print("  1. oauth.yandex.ru → новое приложение, права metrika:read")
        print("  2. откройте https://oauth.yandex.ru/authorize?response_type=token&client_id=<ID>")
        print("  3. скопируйте access_token в .env строкой METRIKA_TOKEN=...")
        sys.exit(3)

    try:
        data = fetch(token, cid, days)
    except urllib.error.HTTPError as exc:
        print("Метрика ответила %s: %s" % (exc.code, exc.read().decode("utf-8", "replace")[:300]))
        sys.exit(1)
    except urllib.error.URLError as exc:
        print("Сеть недоступна: %s" % exc.reason)
        sys.exit(1)

    rows = []
    for item in data.get("data", []):
        dims = item.get("dimensions") or [{}]
        path = dims[0].get("name") or ""
        metrics = item.get("metrics") or [0, 0, 0, 0]
        rows.append({
            "path": path,
            "pageviews": int(metrics[0]),
            "users": int(metrics[1]),
            "bounce": round(metrics[2], 1),
            "avg_seconds": round(metrics[3], 0),
        })

    by_rubric: dict[str, dict[str, float]] = defaultdict(lambda: {"views": 0, "users": 0, "seconds": 0, "n": 0})
    for row in rows:
        r = rubric_of(row["path"])
        agg = by_rubric[r]
        agg["views"] += row["pageviews"]
        agg["users"] += row["users"]
        agg["seconds"] += row["avg_seconds"]
        agg["n"] += 1

    summary = {
        "counter": cid,
        "days": days,
        "generated": date.today().isoformat(),
        "top_pages": rows[:20],
        "rubrics": [
            {
                "rubric": k,
                "pageviews": v["views"],
                "users": v["users"],
                "avg_seconds": round(v["seconds"] / v["n"]) if v["n"] else 0,
                "articles": v["n"],
            }
            for k, v in sorted(by_rubric.items(), key=lambda kv: -kv[1]["views"])
        ],
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print("Метрика, счётчик %s, последние %d дней\n" % (cid, days))
    print("По темам:")
    for r in summary["rubrics"]:
        print("  %-16s просмотры %-5d читатели %-4d среднее время %3d с  статей %d"
              % (r["rubric"], r["pageviews"], r["users"], r["avg_seconds"], r["articles"]))
    print("\nТоп страниц:")
    for p in summary["top_pages"][:10]:
        print("  %-55s %4d просм.  %3d с" % (p["path"][:55], p["pageviews"], p["avg_seconds"]))
    print("\nОтчёт сохранён: analytics/report.json")


if __name__ == "__main__":
    main()
