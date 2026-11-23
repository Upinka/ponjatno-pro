#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Наблюдение за активацией домена: whois-статус, делегирование DNS, доступность сайта.

Пишет изменения в logs/domain_watch.log и присылает сообщение в Telegram
при каждом изменении состояния (а не каждый круг).

Запуск:
    python scripts/watch_domain.py --domain ponjatno-pro.ru
    python scripts/watch_domain.py --once        # один замер и выход
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "domain_watch.log"

GITHUB_IPS = {
    "185.199.108.153", "185.199.109.153",
    "185.199.110.153", "185.199.111.153",
}


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = "[%s] %s" % (datetime.now().strftime("%d.%m %H:%M:%S"), msg)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def tg(text: str) -> None:
    env = load_env()
    token, chat = env.get("TG_BOT_TOKEN"), env.get("TG_CHAT_ID")
    if not token or not chat:
        return
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        urllib.request.urlopen(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=data, timeout=20)
    except Exception as exc:  # noqa: BLE001
        log("telegram: не удалось отправить (%s)" % exc)


def whois_state(domain: str) -> str:
    try:
        url = "https://api.whois.vu/?q=" + urllib.parse.quote(domain)
        req = urllib.request.Request(url, headers={"User-Agent": "dsh"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        return "whois-ошибка: %s" % exc
    if data.get("available") == "yes":
        return "не зарегистрирован"
    statuses = data.get("statuses") or []
    state = ", ".join(statuses) if statuses else "нет статуса"
    updated = (data.get("whois") or "")
    marker = "VERIFIED" if "UNVERIFIED" not in state else "UNVERIFIED"
    return "%s [%s]" % (state, marker)


def dns_ips(domain: str) -> set[str]:
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    return ips


def site_code(domain: str) -> int:
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request("https://%s/" % domain, headers={"User-Agent": "dsh"})
        with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001
        return 0


def snapshot(domain: str) -> tuple[str, str, int]:
    state = whois_state(domain)
    ips = dns_ips(domain)
    if not ips:
        dns_txt = "нет записей"
    elif ips & GITHUB_IPS:
        dns_txt = "GitHub Pages (" + ", ".join(sorted(ips & GITHUB_IPS)) + ")"
    else:
        dns_txt = ", ".join(sorted(ips))
    return state, dns_txt, site_code(domain)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    domain = args[args.index("--domain") + 1] if "--domain" in args else "ponjatno-pro.ru"
    once = "--once" in args
    interval = 300
    total_minutes = 240

    log("=== наблюдение за %s ===" % domain)
    prev = snapshot(domain)
    log("whois: %s | DNS: %s | сайт: %s" % prev)
    if once:
        return

    deadline = time.time() + total_minutes * 60
    while time.time() < deadline:
        time.sleep(interval)
        cur = snapshot(domain)
        if cur != prev:
            log("ИЗМЕНЕНИЕ: whois: %s | DNS: %s | сайт: %s" % cur)
            if "GitHub Pages" in cur[1] or cur[2] == 200:
                tg("✅ Домен <b>%s</b> активирован.\nwhois: %s\nDNS: %s\nсайт: HTTP %d"
                   % (domain, cur[0], cur[1], cur[2]))
            elif "UNVERIFIED" not in cur[0]:
                tg("🔔 Домен <b>%s</b>: статус подтверждения изменился.\nwhois: %s\nDNS: %s"
                   % (domain, cur[0], cur[1]))
            prev = cur
        else:
            log("без изменений: whois: %s | DNS: %s | сайт: %s" % cur)
    log("=== наблюдение завершено ===")


if __name__ == "__main__":
    main()
