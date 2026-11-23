#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка собранного сайта и RSS на соответствие требованиям «Дзен для медиа».

Запуск:  python scripts/validate.py
Код возврата 1 — есть ошибки, которые почти наверняка приведут к отказу Дзена.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
PUBLIC = ROOT / "public"

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}

ALLOWED_TAGS = {
    "p", "h2", "h3", "ul", "ol", "li", "a", "b", "i", "u", "s",
    "blockquote", "figure", "img", "figcaption", "video", "source", "br",
}

errors: list[str] = []
warnings: list[str] = []
oks: list[str] = []


def ok(msg: str) -> None:
    oks.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def err(msg: str) -> None:
    errors.append(msg)


def check_feed() -> None:
    feed_path = PUBLIC / CONFIG["feed"]["path"]
    if not feed_path.exists():
        err("Нет файла ленты: %s" % feed_path)
        return
    try:
        tree = ET.parse(feed_path)
    except ET.ParseError as exc:
        err("Лента не парсится как XML: %s" % exc)
        return
    ok("Лента — валидный XML")

    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        err("В ленте нет <channel>")
        return

    for tag in ("title", "link", "description", "language"):
        node = channel.find(tag)
        if node is None or not (node.text or "").strip():
            err("В <channel> нет обязательного элемента <%s>" % tag)
    if not errors:
        ok("Обязательные элементы channel на месте")

    items = channel.findall("item")
    if len(items) < 10:
        err("В ленте %d материалов, Дзен требует минимум 10 при первой подаче "
            "(увеличьте feed.window_days или добавьте статьи)" % len(items))
    else:
        ok("Материалов в ленте: %d" % len(items))

    base = CONFIG["site"]["base_url"].rstrip("/")
    base_host = urlparse(base).netloc
    seen_guid: set[str] = set()

    for i, item in enumerate(items, 1):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()

        label = title[:40] or "item #%d" % i
        for tag, value in (("title", title), ("link", link), ("guid", guid),
                           ("pubDate", pub), ("description", item.findtext("description"))):
            if not value or not str(value).strip():
                err("[%s] пустой обязательный элемент <%s>" % (label, tag))

        if guid:
            if guid in seen_guid:
                err("[%s] повторяющийся guid — Дзен создаст дубликат" % label)
            seen_guid.add(guid)

        if link:
            parsed = urlparse(link)
            if parsed.netloc != base_host:
                err("[%s] домен ссылки (%s) не совпадает с base_url (%s)"
                    % (label, parsed.netloc, base_host))
            if parsed.query:
                err("[%s] в ссылке есть параметры (%s) — Дзен требует ЧПУ без UTM"
                    % (label, parsed.query))
            if not link.endswith("/"):
                warn("[%s] ссылка без завершающего слэша" % label)

        body = item.find("content:encoded", NS)
        if body is None or not (body.text or "").strip():
            err("[%s] нет полного текста в <content:encoded>" % label)
        else:
            tags = {t.lower() for t in re.findall(r"<\s*([a-zA-Z0-9]+)", body.text)}
            bad = tags - ALLOWED_TAGS
            if bad:
                warn("[%s] теги вне рекомендованного списка: %s"
                     % (label, ", ".join(sorted(bad))))
            if "]]>" in body.text:
                err("[%s] в content:encoded есть ]]> — CDATA сломается" % label)

        enclosure = item.find("enclosure")
        if enclosure is None:
            warn("[%s] нет обложки (<enclosure>) — карточка будет без картинки" % label)
        else:
            url = enclosure.get("url", "")
            if url.startswith("http") and urlparse(url).netloc != base_host:
                err("[%s] обложка на чужом домене" % label)
            local = PUBLIC / "static" / "covers" / url.rsplit("/", 1)[-1]
            if local.exists():
                try:
                    from PIL import Image
                    with Image.open(local) as im:
                        if im.width < 700:
                            err("[%s] обложка %d px — Дзен требует минимум 700 px"
                                % (label, im.width))
                except ImportError:
                    pass
            else:
                warn("[%s] файл обложки не найден локально: %s" % (label, local.name))

        # страница статьи должна существовать
        if link.startswith(base):
            rel = link[len(base):].strip("/")
            page = PUBLIC / rel / "index.html"
            if not page.exists():
                err("[%s] нет страницы статьи: %s" % (label, page.relative_to(PUBLIC)))


def check_site() -> None:
    robots = PUBLIC / "robots.txt"
    if not robots.exists():
        err("Нет robots.txt")
    else:
        lines = [line.strip() for line in robots.read_text(encoding="utf-8").splitlines()]
        feed = "/" + CONFIG["feed"]["path"].lstrip("/")
        disallow_root = any(line == "Disallow: /" for line in lines)
        feed_allowed = any(
            line.lower().startswith("allow:")
            and line.split(":", 1)[1].strip().endswith(feed)
            for line in lines
        )
        if disallow_root and not feed_allowed:
            err("robots.txt запрещает обход ленты (Disallow: / без Allow для %s)" % feed)
        elif feed_allowed:
            ok("robots.txt разрешает обход ленты")
        else:
            warn("В robots.txt нет явного Allow для %s — проверьте правило Disallow" % feed)

    if (PUBLIC / "index.html").exists():
        ok("Главная страница собрана")
    else:
        err("Нет index.html")

    base = CONFIG["site"]["base_url"]
    if "example" in base:
        warn("base_url всё ещё содержит example — замените на купленный домен")

    domain = urlparse(base).netloc
    if any(ord(ch) > 127 for ch in domain):
        err("Домен содержит не-ASCII символы (IDN) — Дзен такие сайты не принимает")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    check_feed()
    check_site()

    for line in oks:
        print("  OK    " + line)
    for line in warnings:
        print("  WARN  " + line)
    for line in errors:
        print("  ERROR " + line)

    print("\nИтого: %d ок, %d предупреждений, %d ошибок"
          % (len(oks), len(warnings), len(errors)))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
