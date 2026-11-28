#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Публикация статьи в Telegram-канал, откуда её заберёт @zen_sync_bot.

Схема: мы постим в свой Telegram-канал → Синхробот Дзена копирует пост
в канал Дзена (официальный путь, без cookies и взлома).

    python publish_to_channel.py --slug igry-zimy-2026-relizy-instrukciya --channel @my_channel
    python publish_to_channel.py --slug ... --channel -1001234567890 --dry-run

Нужно:
  • бот @MoyLichno_bot добавлен админом в канал (он публикует);
  • @zen_sync_bot подключён к этому каналу (он переносит в Дзен).
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILES = [ROOT / ".env", ROOT.parent / "tg-ai" / ".env"]
TG_LIMIT = 1024  # подпись к фото
PROXY_CACHE: dict[str, str | None] = {}
PROXY_CANDIDATES = ["http://127.0.0.1:10809", "http://127.0.0.1:10808"]


def proxy_url(env: dict[str, str]) -> str | None:
    """Выбираем прокси: из окружения, из .env или первый живой локальный."""
    explicit = env.get("TG_PROXY") or os.environ.get("HTTPS_PROXY")
    if explicit:
        return explicit
    for url in PROXY_CANDIDATES:
        host, port = url.split("//")[1].split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=1):
                return url
        except OSError:
            continue
    return None


def make_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    for key in ("TG_BOT_TOKEN", "TG_CHANNEL_ID"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def parse_article(slug: str) -> dict:
    sys.path.insert(0, str(ROOT))
    import build  # noqa: E402

    for a in build.load_articles():
        if a.slug == slug:
            return {
                "title": a.title,
                "rubric": a.rubric,
                "lead": a.description,
                "body": build.md_to_html(a.body_md),
                "cover": ROOT / "static" / "covers" / a.cover if a.cover else None,
                "url": "https://ponjatno-pro.ru%s" % a.url_path,
            }
    raise SystemExit("Статья не найдена: " + slug)


def plain(html: str) -> str:
    text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n\1\n", html, flags=re.S)
    text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\n\1\n", text, flags=re.S)
    text = re.sub(r"<li>(.*?)</li>", r"— \1\n", text, flags=re.S)
    text = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>", r"«\1»", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&laquo;", "«").replace("&raquo;", "»").replace("&mdash;", "—")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_caption(article: dict) -> str:
    """Заголовок + начало текста: Дзен берёт заголовком первое предложение."""
    body = plain(article["body"])
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    start = article["lead"].strip() if article["lead"] else (paragraphs[0] if paragraphs else "")
    caption = "%s\n\n%s" % (article["title"], start)
    return caption[:TG_LIMIT]


def send_photo(token: str, channel: str, image: Path, caption: str) -> dict:
    boundary = "----dsh" + str(int(Path().stat().st_mtime)) if False else "----dshboundary"
    parts: list[bytes] = []
    for name, value in (("chat_id", channel), ("caption", caption), ("parse_mode", "HTML")):
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, name, value)).encode("utf-8"))
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"%s\"\r\n"
                  "Content-Type: image/jpeg\r\n\r\n" % (boundary, image.name)).encode("utf-8"))
    parts.append(image.read_bytes())
    parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendPhoto" % token, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": exc.read().decode("utf-8", "replace")}


def send_text(token: str, channel: str, text: str) -> dict:
    data = urllib.parse.urlencode({"chat_id": channel, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token,
                                 data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": exc.read().decode("utf-8", "replace")}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    if "--slug" not in args:
        print(__doc__)
        sys.exit(2)
    slug = args[args.index("--slug") + 1]
    env = load_env()
    channel = args[args.index("--channel") + 1] if "--channel" in args else env.get("TG_CHANNEL_ID", "")
    dry_run = "--dry-run" in args

    article = parse_article(slug)
    caption = build_caption(article)
    print("статья:", article["title"])
    print("канал:", channel or "—")
    print("обложка:", article["cover"])
    print("--- подпись к посту ---")
    print(caption)

    if dry_run:
        print("\n[сухой прогон] ничего не отправлено")
        return
    if not channel:
        print("\nНет канала: передайте --channel @name или задайте TG_CHANNEL_ID")
        sys.exit(2)

    token = env.get("TG_BOT_TOKEN")
    if not token:
        print("\nНет TG_BOT_TOKEN в окружении или .env")
        sys.exit(2)

    if article["cover"] and article["cover"].exists():
        result = send_photo(token, channel, article["cover"], caption)
    else:
        result = send_text(token, channel, caption)
    print("\nрезультат:", json.dumps(result, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
