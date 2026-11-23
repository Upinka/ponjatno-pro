#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Доводит переключение сайта на собственный домен без участия человека.

Что делает по шагам:
  1. ждёт, пока домен начнёт резолвиться в адреса GitHub Pages;
  2. меняет base_url в site.config.json, пересобирает сайт;
  3. запускает валидатор: если есть ошибки — откатывает конфиг и выходит;
  4. коммитит и пушит (деплой запустится сам через GitHub Actions);
  5. прописывает Custom domain в GitHub Pages через API;
  6. ждёт, пока https://домен/ и лента начнут отвечать 200.

Запуск:
    python scripts/finish_domain.py --domain ponjatno-pro.ru
    python scripts/finish_domain.py --check-only        # только проверить DNS

Лог: logs/finish_domain.log
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "site.config.json"
LOG = ROOT / "logs" / "finish_domain.log"

GITHUB_PAGES_IPS = {
    "185.199.108.153", "185.199.109.153",
    "185.199.110.153", "185.199.111.153",
}
REPO = "Upinka/ponjatno-pro"

# Git мог быть установлен уже после запуска сессии: PATH процесса может его не видеть.
GIT = shutil.which("git") or next(
    (p for p in (r"C:\Program Files\Git\cmd\git.exe",
                 r"C:\Program Files (x86)\Git\cmd\git.exe") if Path(p).exists()),
    "git",
)


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def resolve(domain: str) -> set[str]:
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        return {info[4][0] for info in infos}
    except socket.gaierror:
        return set()


def wait_for_dns(domain: str, minutes: int, every: int = 60) -> bool:
    deadline = time.time() + minutes * 60
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        ips = resolve(domain)
        if ips & GITHUB_PAGES_IPS:
            log("DNS готов (попытка %d): %s" % (attempt, ", ".join(sorted(ips))))
            return True
        log("DNS пока не готов (попытка %d): %s" % (
            attempt, ", ".join(sorted(ips)) if ips else "записи не найдены"))
        time.sleep(every)
    log("DNS не появился за %d минут" % minutes)
    return False


def set_base_url(url: str) -> str | None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    previous = cfg["site"]["base_url"]
    cfg["site"]["base_url"] = url
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log("base_url: %s -> %s" % (previous, url))
    return previous


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    if cmd and cmd[0] == "git":
        cmd = [GIT] + cmd[1:]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def git_token() -> str | None:
    try:
        proc = subprocess.run([GIT, "credential", "fill"], cwd=ROOT,
                              input="protocol=https\nhost=github.com\n\n",
                              capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return None


def api(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "https://api.github.com" + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dsh",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def http_status(url: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dsh"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    domain = "ponjatno-pro.ru"
    if "--domain" in args:
        domain = args[args.index("--domain") + 1]
    wait_minutes = 180
    if "--wait-minutes" in args:
        wait_minutes = int(args[args.index("--wait-minutes") + 1])
    check_only = "--check-only" in args

    log("=== старт: домен %s ===" % domain)

    if not resolve(domain) & GITHUB_PAGES_IPS:
        if check_only:
            log("DNS не готов (проверка по требованию)")
            return 2
        if not wait_for_dns(domain, wait_minutes):
            return 2
    else:
        log("DNS уже готов")

    if check_only:
        return 0

    previous = set_base_url("https://" + domain)

    build = run([sys.executable, "build.py", "--clean"])
    log("build: код %d · %s" % (build.returncode, (build.stdout or build.stderr).strip().splitlines()[-1] if (build.stdout or build.stderr).strip() else ""))
    if build.returncode != 0:
        set_base_url(previous or "")
        log("ОШИБКА сборки, конфиг откачен")
        return 1

    check = run([sys.executable, "scripts/validate.py"])
    log("validate: код %d" % check.returncode)
    if check.returncode != 0:
        set_base_url(previous or "")
        log("ОШИБКА валидации, конфиг откачен:\n" + check.stdout)
        return 1

    run(["git", "add", "-A"])
    commit = run(["git", "-c", "user.name=DSH", "-c", "user.email=dsh@local",
                  "commit", "-m", "config: переключение на домен %s" % domain])
    if commit.returncode not in (0, 1):
        log("git commit: " + commit.stderr.strip())
    push = run(["git", "push", "origin", "main"])
    log("git push: код %d %s" % (push.returncode, push.stderr.strip()[:200]))
    if push.returncode != 0:
        log("ОШИБКА пуша")
        return 1

    token = git_token()
    if token:
        for method in ("PUT", "POST"):
            code, body = api(method, "/repos/%s/pages" % REPO, token,
                             {"cname": domain, "build_type": "workflow", "https_enforced": True})
            log("pages %s: код %d" % (method, code))
            if code in (200, 201, 204):
                break
    else:
        log("токен GitHub не получен, Custom domain нужно выставить вручную")

    log("жду HTTPS на домене (до 15 минут)")
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        root_code = http_status("https://%s/" % domain)
        feed_code = http_status("https://%s/feed.xml" % domain)
        if root_code == 200 and feed_code == 200:
            log("ДОМЕН РАБОТАЕТ: https://%s/ и feed.xml отдают 200" % domain)
            return 0
        log("пока: / = %d, feed = %d" % (root_code, feed_code))
        time.sleep(60)

    log("домен не поднялся за 15 минут — проверьте DNS и статус сертификата в Settings → Pages")
    return 3


if __name__ == "__main__":
    sys.exit(main())
