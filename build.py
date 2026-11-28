#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор статического сайта-источника для Дзена («Дзен для медиа» + RSS 2.0).

Что делает:
  * читает статьи из content/<рубрика>/<slug>.md с front matter;
  * собирает HTML-сайт в public/ (ЧПУ-адреса, без UTM и параметров);
  * формирует feed.xml по требованиям Дзена: RSS 2.0, content:encoded в CDATA,
    guid, pubDate в RFC 822 (+0300), enclosure для обложки;
  * создаёт robots.txt, sitemap.xml, CNAME и копирует файлы подтверждения прав.

Только стандартная библиотека Python. Запуск:
    python build.py
    python build.py --clean
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "site.config.json"
CONTENT_DIR = ROOT / "content"
STATIC_DIR = ROOT / "static"
PUBLIC_DIR = ROOT / "public"
ADS_DIR = ROOT / "ads"

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

MSK = timezone(timedelta(hours=3))

# Заполняются в build(): адрес сайта и префикс пути (для хостинга в подкаталоге).
BASE = ""
PREFIX = ""


def rel(path: str) -> str:
    """Внутренняя ссылка с учётом подкаталога, например username.github.io/repo."""
    return (PREFIX + path) if PREFIX else path


# --------------------------------------------------------------------------- #
#  Утилиты
# --------------------------------------------------------------------------- #
def ep(text: str) -> str:
    """Экранирование текста для HTML/XML."""
    return html.escape(text, quote=False)


def ea(text: str) -> str:
    """Экранирование для XML-атрибутов."""
    return html.escape(text, quote=True)


def rfc822(dt: datetime) -> str:
    """RFC 822 без зависимости от локали (Windows отдаёт русские имена дней)."""
    return "%s, %02d %s %04d %02d:%02d:%02d %s" % (
        WEEKDAYS[dt.weekday()], dt.day, MONTHS[dt.month - 1], dt.year,
        dt.hour, dt.minute, dt.second, dt.strftime("%z"),
    )


def human_date(dt: datetime) -> str:
    return "%d %s %d" % (dt.day, MONTHS_RU[dt.month - 1], dt.year)


def reading_time(md: str) -> int:
    """Примерное время чтения в минутах (180 слов в минуту)."""
    words = len(re.sub(r"[#>*_`\[\]()!-]", " ", md).split())
    return max(1, round(words / 180))


def iso_date(dt: datetime) -> str:
    return dt.isoformat()


# --------------------------------------------------------------------------- #
#  Разбор статей
# --------------------------------------------------------------------------- #
@dataclass
class Article:
    slug: str
    rubric: str
    title: str
    description: str
    date: datetime
    author: str
    tags: list
    cover: str
    body_md: str
    source: Path
    feed_exclude: bool = False
    kind: str = "article"   # article | note | instruction

    @property
    def url_path(self) -> str:
        return "/%s/%s/" % (self.rubric, self.slug)


def parse_front_matter(raw: str, src: Path) -> tuple[dict, str]:
    if not raw.startswith("---"):
        raise SystemExit("Нет front matter в %s (файл должен начинаться с ---)" % src)
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise SystemExit("Незакрытый front matter в %s" % src)
    meta: dict = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, parts[2].lstrip("\n")


def load_articles() -> list[Article]:
    articles: list[Article] = []
    skipped: list[str] = []
    for path in sorted(CONTENT_DIR.rglob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)
        if meta.get("status", "published").lower() == "draft":
            skipped.append(str(path.relative_to(ROOT)))
            continue
        raw_date = meta.get("date")
        if not raw_date:
            raise SystemExit("В %s не указана date" % path)
        dt = datetime.fromisoformat(raw_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=MSK)
        dt = dt.astimezone(MSK)
        articles.append(Article(
            slug=meta.get("slug") or path.stem,
            rubric=path.parent.name,
            title=meta.get("title", path.stem),
            description=meta.get("description", ""),
            date=dt,
            author=meta.get("author", ""),
            tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
            cover=meta.get("cover", ""),
            body_md=body,
            source=path,
            feed_exclude=meta.get("feed_exclude", "").lower() in ("true", "1", "yes"),
            kind=(meta.get("kind") or "article").strip().lower(),
        ))
    articles.sort(key=lambda a: a.date, reverse=True)
    if skipped:
        print("  черновики пропущены: %d" % len(skipped))
    return articles


# --------------------------------------------------------------------------- #
#  Markdown (подмножество, совместимое с разрешённым в Дзене HTML)
# --------------------------------------------------------------------------- #
def inline(text: str) -> str:
    out = ep(text)
    # ссылки [текст](url) — только http(s) или внутренние
    def _link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("/")):
            return label
        external = url.startswith("http")
        attrs = ' rel="nofollow noopener" target="_blank"' if external else ""
        return '<a href="%s"%s>%s</a>' % (ea(url), attrs, label)

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", out)
    return out


def md_to_html(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    para: list[str] = []
    i = 0

    def flush_para() -> None:
        if para:
            blocks.append("<p>%s</p>" % inline(" ".join(x.strip() for x in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        if stripped.startswith("### "):
            flush_para()
            blocks.append("<h3>%s</h3>" % inline(stripped[4:]))
            i += 1
            continue

        if stripped.startswith("## "):
            flush_para()
            blocks.append("<h2>%s</h2>" % inline(stripped[3:]))
            i += 1
            continue

        m_img = re.match(r"^!\[(.*?)\]\(([^)\s]+)\)$", stripped)
        if m_img:
            flush_para()
            alt, src = m_img.group(1), m_img.group(2)
            cap = "<figcaption>%s</figcaption>" % inline(alt) if alt else ""
            blocks.append('<figure><img src="%s" alt="%s">%s</figure>'
                          % (ea(src), ea(alt), cap))
            i += 1
            continue

        if re.match(r"^[-*] ", stripped):
            flush_para()
            items = []
            while i < len(lines) and re.match(r"^[-*] ", lines[i].strip()):
                items.append("<li>%s</li>" % inline(lines[i].strip()[2:]))
                i += 1
            blocks.append("<ul>%s</ul>" % "".join(items))
            continue

        if re.match(r"^\d+\. ", stripped):
            flush_para()
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i].strip()):
                items.append("<li>%s</li>" % inline(re.sub(r"^\d+\. ", "", lines[i].strip())))
                i += 1
            blocks.append("<ol>%s</ol>" % "".join(items))
            continue

        if stripped.startswith("> "):
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:])
                i += 1
            blocks.append("<blockquote><p>%s</p></blockquote>" % inline(" ".join(quote)))
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return "\n".join(blocks)


# --------------------------------------------------------------------------- #
#  Шаблоны
# --------------------------------------------------------------------------- #
def nav_html(rubrics: list[dict], active: str | None = None) -> str:
    items = ['<a class="nav__link%s" href="%s">Главная</a>'
             % (" nav__link--active" if active == "index" else "", rel("/"))]
    for r in rubrics:
        cls = " nav__link--active" if active == r["slug"] else ""
        items.append('<a class="nav__link%s" href="%s">%s</a>'
                     % (cls, rel("/%s/" % r["slug"]), ep(r["title"])))
    return "\n".join(items)


def head_html(cfg: dict, title: str, description: str, canonical: str,
              og_type: str = "website", cover_url: str = "") -> str:
    base = cfg["site"]["base_url"].rstrip("/")
    metrika = cfg.get("analytics", {}).get("yandex_metrika_id")
    # Код счётчика: приоритет — файл analytics/metrika.html (вставляется дословно,
    # как можно раньше в <head>). Если файла нет — генерируем минимальный сниппет.
    counter_html = ""
    snippet_file = cfg.get("analytics", {}).get("metrika_snippet_file")
    if snippet_file:
        snippet_path = ROOT / snippet_file
        if snippet_path.exists():
            counter_html = snippet_path.read_text(encoding="utf-8").strip() + "\n"
        else:
            print("  ВНИМАНИЕ: нет файла счётчика %s" % snippet_path)
    if not counter_html and metrika:
        counter_html = (
            '<script>(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};'
            'm[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}'
            'k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})'
            '(window,document,"script","https://mc.yandex.ru/metrika/tag.js","ym");'
            'ym(%s,"init",{clickmap:true,trackLinks:true,accurateTrackBounce:true});</script>'
            '<noscript><div><img src="https://mc.yandex.ru/watch/%s" style="position:absolute;left:-9999px" alt=""></div></noscript>\n'
            % (metrika, metrika)
        )
    og_image = ('<meta property="og:image" content="%s">' % ea(cover_url)) if cover_url else ""
    stylesheet = '<link rel="stylesheet" href="%s">\n' % rel("/static/style.css")
    verify_tags = ""
    for tag in cfg.get("verification", {}).get("meta_tags", []) or []:
        name, content = tag.get("name"), tag.get("content")
        if name and content:
            verify_tags += '<meta name="%s" content="%s">\n' % (ea(name), ea(content))
    # рекламные пиксели (Дзен, ВК, любые) — вставляются как есть
    for pixel in cfg.get("analytics", {}).get("pixels", []) or []:
        html_code = pixel.get("html") or ""
        if html_code:
            verify_tags += html_code.strip() + "\n"
    return (
        '<!DOCTYPE html>\n<html lang="ru">\n<head>\n'
        '<meta charset="utf-8">\n'
        '%s'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n"
        '<meta name="description" content="%s">\n'
        '<link rel="canonical" href="%s">\n'
        '<link rel="icon" href="%s" type="image/svg+xml">\n'
        '<link rel="icon" href="%s" sizes="32x32" type="image/png">\n'
        '<link rel="apple-touch-icon" href="%s">\n'
        '<link rel="alternate" type="application/rss+xml" title="RSS" href="%s/%s">\n'
        '<meta property="og:type" content="%s">\n'
        '<meta property="og:title" content="%s">\n'
        '<meta property="og:description" content="%s">\n'
        '<meta property="og:url" content="%s">\n%s'
        '%s'
        '%s\n</head>\n'
        % (counter_html,
           ep(title), ea(description), ea(canonical),
           rel("/static/favicon.svg"), rel("/static/favicon-32.png"),
           rel("/static/apple-touch-icon.png"),
           base, cfg["feed"]["path"],
           og_type, ea(title), ea(description), ea(canonical), og_image,
           stylesheet, verify_tags)
    )


def page_html(cfg: dict, title: str, description: str, canonical: str,
              content: str, active: str | None = None, og_type: str = "website",
              cover_url: str = "", ad_top: str = "", ad_bottom: str = "") -> str:
    base = cfg["site"]["base_url"].rstrip("/")
    site = cfg["site"]
    links = cfg.get("links", {})
    dzen_link = (' &middot; <a href="%s" rel="noopener">Мы в Дзене</a>' % ea(links["dzen"])
                 if links.get("dzen") else "")
    tg_link = (' &middot; <a href="%s" rel="noopener">Telegram</a>' % ea(links["telegram"])
               if links.get("telegram") else "")
    return (
        head_html(cfg, title, description, canonical, og_type, cover_url)
        + "<body>\n"
        '<header class="site-header">\n'
        '<a class="logo" href="%s">%s</a>\n'
        '<p class="tagline">%s</p>\n'
        '<nav class="nav">%s</nav>\n'
        '</header>\n<main class="wrap">\n%s\n%s\n%s\n</main>\n'
        '<footer class="site-footer">\n'
        '<p>%s &middot; <a href="%s">RSS</a>%s%s</p>\n'
        '<p class="muted">%s</p>\n'
        '</footer>\n%s</body>\n</html>\n'
        % (rel("/"), ep(site["title"]), ep(site.get("tagline", "")),
           nav_html(cfg["rubrics"], active), ad_top, content, ad_bottom,
           ep(site["title"]), rel("/" + cfg["feed"]["path"].lstrip("/")),
           dzen_link, tg_link,
           ep(site.get("copyright", "")), events_script(cfg))
    )


def events_script(cfg: dict) -> str:
    """События для Метрики/пикселей: открытие статьи, полное чтение, внешний переход."""
    metrika = cfg.get("analytics", {}).get("yandex_metrika_id")
    if not metrika:
        return ""
    return (
        "<script>\n"
        "(function(){\n"
        "  var ID=%s;\n"
        "  function goal(n){ try{ if(window.ym){ ym(ID,'reachGoal',n); } }catch(e){} }\n"
        "  if (document.querySelector('.post')) { goal('article_open'); }\n"
        "  var sent=false;\n"
        "  function fullRead(){\n"
        "    if (sent) return; sent=true; goal('article_full_read');\n"
        "  }\n"
        "  window.addEventListener('scroll', function(){\n"
        "    var d=document.documentElement;\n"
        "    if (!d.scrollHeight) return;\n"
        "    if ((d.scrollTop+window.innerHeight)/d.scrollHeight > 0.9) fullRead();\n"
        "  }, {passive:true});\n"
        "  document.addEventListener('click', function(e){\n"
        "    var a=e.target && e.target.closest ? e.target.closest('a') : null;\n"
        "    if (!a || !a.hostname) return;\n"
        "    if (a.hostname !== location.hostname) goal('external_click');\n"
        "  }, true);\n"
        "})();\n"
        "</script>\n"
        % json.dumps(metrika)
    )


def rubric_title(cfg: dict, slug: str) -> str:
    for r in cfg["rubrics"]:
        if r["slug"] == slug:
            return r["title"]
    return ""


def article_card(a: Article, cfg: dict) -> str:
    cover = ""
    if a.cover:
        cover = '<img class="card__img" src="%s" alt="%s" loading="lazy">' % (
            ea(cover_url(cfg, a.cover)), ea(a.title))
    chip = "" if a.cover else ('<p class="card__rubric">%s</p>\n' % ep(rubric_title(cfg, a.rubric)))
    kind_badge = ""
    if a.kind in ("note", "instruction"):
        label = "Заметка" if a.kind == "note" else "Инструкция"
        kind_badge = '<p class="card__kind">%s</p>\n' % label
    return (
        '<article class="card card--%s">\n'
        '<a class="card__link" href="%s">\n%s'
        '<div class="card__body">\n'
        '%s%s'
        '<h2 class="card__title">%s</h2>\n'
        '<p class="card__desc">%s</p>\n'
        '<p class="card__meta">%s &middot; %d мин чтения</p>\n'
        '</div>\n'
        '</a>\n</article>\n'
        % (ea(a.kind), rel(a.url_path), cover, kind_badge, chip, ep(a.title),
           ep(a.description), human_date(a.date), reading_time(a.body_md))
    )


def cover_url(cfg: dict, filename: str) -> str:
    if filename.startswith("http"):
        return filename
    return "%s/static/covers/%s" % (cfg["site"]["base_url"].rstrip("/"), filename)


# --------------------------------------------------------------------------- #
#  Сборка
# --------------------------------------------------------------------------- #
def build(clean: bool = False) -> None:
    if not CONFIG_PATH.exists():
        raise SystemExit("Нет site.config.json рядом с build.py")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    base = cfg["site"]["base_url"].rstrip("/")
    global BASE, PREFIX
    BASE = base
    PREFIX = urlparse(base).path.rstrip("/")

    if clean and PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    articles = load_articles()
    if not articles:
        raise SystemExit("Статьи не найдены в content/")

    rubrics = {r["slug"]: r for r in cfg["rubrics"]}
    unknown = {a.rubric for a in articles} - set(rubrics)
    if unknown:
        raise SystemExit("Рубрики без описания в site.config.json: %s" % ", ".join(sorted(unknown)))

    # рекламный код РСЯ (вставляется как есть)
    ad_html = ""
    ads = cfg.get("ads", {})
    if ads.get("enabled"):
        snippet_path = ADS_DIR / ads.get("rsy_snippet", "rsy.html")
        if snippet_path.exists():
            ad_html = snippet_path.read_text(encoding="utf-8")
        else:
            print("  ВНИМАНИЕ: ads.enabled=true, но %s не найден" % snippet_path)
    ad_top = '<div class="ad-slot">%s</div>' % ad_html if ad_html else ""
    ad_bottom = ad_top

    # --- статьи -----------------------------------------------------------
    for a in articles:
        body_html = md_to_html(a.body_md)
        cover_block = ""
        cover_abs = ""
        if a.cover:
            cover_abs = cover_url(cfg, a.cover)
            cover_block = '<img class="hero" src="%s" alt="%s">' % (ea(cover_abs), ea(a.title))
        jsonld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": a.title,
            "description": a.description,
            "datePublished": iso_date(a.date),
            "author": {"@type": "Person", "name": a.author or cfg["site"]["author"]},
            "image": cover_abs or None,
            "publisher": {"@type": "Organization", "name": cfg["site"]["title"]},
            "mainEntityOfPage": base + a.url_path,
        }
        if jsonld["image"] is None:
            jsonld.pop("image")
        related = [x for x in articles if x.rubric == a.rubric and x.slug != a.slug][:3]
        related_html = ""
        if related:
            related_html = ('<aside class="related"><h2>Читайте также</h2><ul>%s</ul></aside>'
                            % "".join('<li><a href="%s">%s</a></li>' % (rel(x.url_path), ep(x.title))
                                      for x in related))
        content = (
            '<article class="post">\n'
            '<h1 class="post__title">%s</h1>\n'
            '<p class="post__meta">%s &middot; %s &middot; %s &middot; %d мин чтения</p>\n'
            "%s\n%s\n%s"
            '<p class="post__back"><a href="%s">&larr; Все статьи рубрики</a></p>\n'
            '</article>\n'
            '<script type="application/ld+json">%s</script>\n'
            % (ep(a.title), human_date(a.date), ep(rubrics[a.rubric]["title"]),
               ep(a.author or cfg["site"]["author"]), reading_time(a.body_md),
               cover_block, body_html, related_html, rel("/%s/" % a.rubric),
               json.dumps(jsonld, ensure_ascii=False))
        )
        out = PUBLIC_DIR / a.rubric / a.slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            page_html(cfg, "%s — %s" % (a.title, cfg["site"]["title"]), a.description,
                      base + a.url_path, content, active=a.rubric, og_type="article",
                      cover_url=cover_abs, ad_top=ad_top, ad_bottom=ad_bottom),
            encoding="utf-8",
        )

    # --- главная ----------------------------------------------------------
    cards = "".join(article_card(a, cfg) for a in articles[:cfg.get("index_limit", 12)])
    index_content = (
        '<h1 class="page-title">%s</h1>\n<p class="page-lead">%s</p>\n<div class="cards">%s</div>'
        % (ep(cfg["site"]["title"]), ep(cfg["site"].get("description", "")), cards)
    )
    (PUBLIC_DIR / "index.html").write_text(
        page_html(cfg, "%s — %s" % (cfg["site"]["title"], cfg["site"].get("tagline", "")),
                  cfg["site"].get("description", ""), base + "/",
                  index_content, active="index", ad_top=ad_top),
        encoding="utf-8",
    )

    # --- рубрики ----------------------------------------------------------
    for slug, r in rubrics.items():
        items = [a for a in articles if a.rubric == slug]
        content = ('<h1 class="page-title">%s</h1>\n<p class="page-lead">%s</p>\n<div class="cards">%s</div>'
                   % (ep(r["title"]), ep(r.get("description", "")),
                      "".join(article_card(a, cfg) for a in items) or "<p>Пока пусто.</p>"))
        out = PUBLIC_DIR / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            page_html(cfg, "%s — %s" % (r["title"], cfg["site"]["title"]),
                      r.get("description", ""), "%s/%s/" % (base, slug),
                      content, active=slug, ad_top=ad_top),
            encoding="utf-8",
        )

    # --- RSS --------------------------------------------------------------
    feed_cfg = cfg["feed"]
    window_days = int(feed_cfg.get("window_days", 3))
    min_items = int(feed_cfg.get("min_items", 10))
    since = datetime.now(MSK) - timedelta(days=window_days)
    available = [a for a in articles if not a.feed_exclude]
    in_window = [a for a in available if a.date >= since][
        : int(feed_cfg.get("max_items", 50))]
    # Дзен требует минимум 10 при первой подаче: если в окне мало — добираем свежими
    if len(in_window) < min_items:
        in_window = available[:max(min_items, len(in_window))]

    items_xml = []
    for a in in_window:
        abs_link = base + a.url_path
        body_html = md_to_html(a.body_md).replace("]]>", "]]&gt;")
        enclosure = ""
        if a.cover:
            size = 0
            cover_file = STATIC_DIR / "covers" / a.cover
            if cover_file.exists():
                size = cover_file.stat().st_size
            ext = a.cover.rsplit(".", 1)[-1].lower()
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "png": "image/png", "gif": "image/gif"}.get(ext, "image/jpeg")
            enclosure = '\n    <enclosure url="%s" length="%d" type="%s"/>' % (
                ea(cover_url(cfg, a.cover)), size, mime)
        items_xml.append(
            "  <item>\n"
            "    <title>%s</title>\n"
            "    <link>%s</link>\n"
            "    <guid isPermaLink=\"true\">%s</guid>\n"
            "    <pubDate>%s</pubDate>\n"
            "    <author>%s</author>\n"
            "    <category>%s</category>\n"
            "    <category>%s</category>%s\n"
            "    <description>%s</description>\n"
            "    <content:encoded><![CDATA[%s]]></content:encoded>\n"
            "  </item>"
            % (ep(a.title), ea(abs_link), ea(abs_link), rfc822(a.date),
               ep(a.author or cfg["site"]["author"]), ea(feed_cfg.get("category", "native-draft")),
               ea(rubrics[a.rubric]["title"]), enclosure, ep(a.description), body_html)
        )

    feed_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"\n'
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/"\n'
        '     xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
        '     xmlns:media="http://search.yahoo.com/mrss/"\n'
        '     xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>\n"
        "  <title>%s</title>\n"
        "  <link>%s/</link>\n"
        "  <description>%s</description>\n"
        "  <language>%s</language>\n"
        "  <atom:link href=\"%s/%s\" rel=\"self\" type=\"application/rss+xml\"/>\n"
        "  <lastBuildDate>%s</lastBuildDate>\n"
        "%s\n"
        "</channel>\n</rss>\n"
        % (ep(cfg["site"]["title"]), ea(base), ep(cfg["site"].get("description", "")),
           cfg["site"].get("language", "ru"), ea(base), feed_cfg["path"],
           rfc822(datetime.now(MSK)), "\n".join(items_xml))
    )
    feed_out = PUBLIC_DIR / feed_cfg["path"]
    feed_out.parent.mkdir(parents=True, exist_ok=True)
    feed_out.write_text(feed_xml, encoding="utf-8")

    # --- sitemap / robots / CNAME / подтверждения -------------------------
    urls = [base + "/"] + ["%s/%s/" % (base, s) for s in rubrics] + \
           [base + a.url_path for a in articles]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n'
               % "\n".join("  <url><loc>%s</loc></url>" % ea(u) for u in urls))
    (PUBLIC_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    robots = ("User-agent: *\nAllow: /\nAllow: %s\nDisallow: /*?*\nSitemap: %s/sitemap.xml\n"
              % (rel("/" + feed_cfg["path"].lstrip("/")), base))
    (PUBLIC_DIR / "robots.txt").write_text(robots, encoding="utf-8")

    host = urlparse(base).netloc
    subpath_hosting = host.startswith("localhost") or any(
        host.endswith(s) for s in (".github.io", ".pages.dev", ".netlify.app"))
    if host and "example" not in host and not subpath_hosting:
        (PUBLIC_DIR / "CNAME").write_text(host + "\n", encoding="utf-8")

    # статика (включая файлы подтверждения прав из static/root/)
    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, PUBLIC_DIR / "static", dirs_exist_ok=True)
        root_extra = STATIC_DIR / "root"
        if root_extra.exists():
            for f in root_extra.iterdir():
                if f.is_file():
                    shutil.copy2(f, PUBLIC_DIR / f.name)
            shutil.rmtree(root_extra)

    print("Готово: %d статей, %d в ленте" % (len(articles), len(in_window)))
    print("Сайт:   %s" % (PUBLIC_DIR / "index.html"))
    print("RSS:    %s" % feed_out)
    if len(in_window) < 10:
        print("  ВНИМАНИЕ: в ленте меньше 10 материалов — Дзен требует минимум 10 "
              "при первой подаче. Увеличьте feed.window_days.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build(clean="--clean" in sys.argv)


if __name__ == "__main__":
    main()
