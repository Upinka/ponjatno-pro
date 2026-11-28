#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Удаление поста из Telegram-канала (отзыв плохой публикации).

    python scripts/delete_channel_post.py --message-id 3
"""

from __future__ import annotations

import json
import re
import socket
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILES = [ROOT / ".env", ROOT.parent / "tg-ai" / ".env"]
PROXIES = ["http://127.0.0.1:10809", "http://127.0.0.1:10808"]


def env_value(key: str) -> str | None:
    for path in ENV_FILES:
        if not path.exists():
            continue
        m = re.search(r"^%s=(.+)$" % re.escape(key), path.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip()
    return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    message_id = args[args.index("--message-id") + 1]
    channel = args[args.index("--channel") + 1] if "--channel" in args else "-1005936256478"

    token = env_value("TG_BOT_TOKEN")
    if not token:
        raise SystemExit("нет TG_BOT_TOKEN")

    proxy = None
    for url in PROXIES:
        host, port = url.split("//")[1].split(":")
        try:
            with socket.create_connection((host, int(port)), timeout=1):
                proxy = url
                break
        except OSError:
            continue

    opener = (urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
              if proxy else urllib.request.build_opener())
    data = urllib.parse.urlencode({"chat_id": channel, "message_id": message_id}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/deleteMessage" % token,
                                 data=data, method="POST")
    with opener.open(req, timeout=30) as resp:
        print(json.loads(resp.read().decode("utf-8", "replace")))


if __name__ == "__main__":
    main()
