#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выбор следующей темы для ежедневной публикации.

    python scripts/next_topic.py --peek     # показать тему, ничего не менять
    python scripts/next_topic.py --take     # взять тему и отметить in_progress
    python scripts/next_topic.py --stats    # сколько тем осталось по рубрикам
    python scripts/next_topic.py --done SLUG  # отметить готовой

Темы хранятся в content-plan.json, статусы: new → in_progress → done.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "content-plan.json"
CONTENT = ROOT / "content"


def load() -> dict:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def save(plan: dict) -> None:
    plan["updated"] = datetime.now().isoformat(timespec="seconds")
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def existing_slugs() -> set[str]:
    return {p.stem for p in CONTENT.rglob("*.md")}


def pick(plan: dict) -> dict | None:
    used = existing_slugs()
    for topic in plan["topics"]:
        if topic["status"] != "new":
            continue
        if topic["slug"] in used:
            topic["status"] = "done"
            continue
        return topic
    return None


RUBRICS = ["rabota-i-dohod", "ii-instrumenty", "dom-i-byt", "karta-i-put"]
SLOT_OFFSET = {"morning": 0, "midday": 1, "evening": 2}


def rubric_for_slot(slot: str, today: date) -> str:
    """Ротация: каждый день у слотов разные рубрики, за 4 дня покрываются все."""
    base = today.toordinal() % len(RUBRICS)
    return RUBRICS[(base + SLOT_OFFSET[slot]) % len(RUBRICS)]


def pick_for_rubric(plan: dict, rubric: str) -> dict | None:
    used = existing_slugs()
    for topic in plan["topics"]:
        if topic["status"] != "new":
            continue
        if topic["slug"] in used:
            topic["status"] = "done"
            continue
        if topic["rubric"] == rubric:
            return topic
    return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    plan = load()

    if "--stats" in args:
        total = len(plan["topics"])
        by_status: dict[str, int] = {}
        by_rubric: dict[str, int] = {}
        for t in plan["topics"]:
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
            if t["status"] == "new":
                by_rubric[t["rubric"]] = by_rubric.get(t["rubric"], 0) + 1
        print("Всего тем: %d" % total)
        print("По статусам: " + ", ".join("%s=%d" % kv for kv in sorted(by_status.items())))
        print("Осталось new по рубрикам:")
        for rubric, count in sorted(by_rubric.items(), key=lambda kv: -kv[1]):
            print("  %-16s %d" % (rubric, count))
        return

    if "--done" in args:
        slug = args[args.index("--done") + 1]
        for t in plan["topics"]:
            if t["slug"] == slug:
                t["status"] = "done"
                save(plan)
                print("отмечено done: " + slug)
                return
        raise SystemExit("Тема не найдена: " + slug)

    if "--current" in args:
        current = next((t for t in plan["topics"] if t["status"] == "in_progress"), None)
        if current is None:
            print("Нет темы в работе. Возьмите новую: --take")
            sys.exit(4)
        print(json.dumps(current, ensure_ascii=False, indent=2))
        return

    if "--slot" in args:
        slot = args[args.index("--slot") + 1]
        if slot not in SLOT_OFFSET:
            raise SystemExit("Слот должен быть morning, midday или evening")
        today = date.today()
        rubric = rubric_for_slot(slot, today)
        topic = pick_for_rubric(plan, rubric)
        if topic is None:
            topic = pick(plan)
            if topic is None:
                print("Тем не осталось — пополните content-plan.json")
                sys.exit(2)
            print("ВНИМАНИЕ: в рубрике %s темы закончились, взята %s"
                  % (rubric, topic["rubric"]), file=sys.stderr)
        topic["status"] = "in_progress"
        topic["taken_at"] = datetime.now().isoformat(timespec="seconds")
        topic["slot"] = slot
        topic["day"] = today.isoformat()
        save(plan)
        print(json.dumps(topic, ensure_ascii=False, indent=2))
        return

    topic = pick(plan)
    if topic is None:
        print("Тем не осталось — пополните content-plan.json")
        sys.exit(2)

    if "--take" in args and "--peek" not in args:
        topic["status"] = "in_progress"
        topic["taken_at"] = datetime.now().isoformat(timespec="seconds")
        save(plan)

    print(json.dumps(topic, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
