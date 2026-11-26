#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/research/pages.py
# Purpose: find and read a company's recent updates on its own website. Free: no API, no credits.
#            1. feeds (RSS / Atom) linked from the home page or at the usual addresses
#            2. the sitemap, using each page's "last changed" date
#            3. news / press / blog pages linked from the home page, and the articles they link to
#          Each page gets a publish date (page tags, structured data, URL, or the text itself)
#          and a language. Lines that repeat across the site (menus, footers, cookie text) are
#          removed, so a menu item like "SAP S/4HANA" can't match on every page.
#          Uses the crawler's polite fetcher: robots.txt, a pause between requests, HTML only.
#--------------------------------------------------------------#

# Imports libraries
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin, urlparse
from job_alerts.crawler import web
#--------------------------------------------------------------#

# Global variables
NEWS_WORDS = re.compile(
    r"news|press|presse|aktuell|neuigkeit|blog|insight|stor(y|ies)|media|medien|magazin|artikel|"
    r"nieuws|actualiteit|noticia|prensa|actualit|communiqu|aktualno|wiadomo|announce|update|"
    r"pressemitteil|mitteilung|bericht|events?(/|$)", re.IGNORECASE)
SKIP_WORDS = re.compile(
    r"karriere|career|jobs?(/|$|-)|stellen|vacature|empleo|emploi|praca|datenschutz|privacy|impressum|imprint|"
    r"cookie|login|cart|warenkorb|/tag/|/tags/|/author/|/page/\d|/search|\?s=|agb|terms|legal|kontakt|contact",
    re.IGNORECASE)
FEED_PATHS = ["/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/news/feed", "/blog/feed", "/de/feed", "/en/feed"]
FILE_ENDINGS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".mp4", ".svg")
MONTHS = {}                                    # month name (any language) -> number
for number, names in enumerate([
        "january januar jänner janvier enero januari stycznia styczeń jan",
        "february februar février febrero februari lutego luty feb",
        "march märz maerz mars marzo maart marca marzec mar",
        "april avril abril kwietnia kwiecień apr",
        "may mai mayo mei maja maj",
        "june juni juin junio czerwca czerwiec jun",
        "july juli juillet julio lipca lipiec jul",
        "august août agosto augustus sierpnia sierpień aug",
        "september septembre septiembre septiembre września wrzesień sep sept",
        "october oktober octobre octubre października październik oct okt",
        "november novembre noviembre listopada listopad nov",
        "december dezember décembre diciembre grudnia grudzień dec dez"], start=1):
    for name in names.split():
        MONTHS[name] = number
MONTH_RE = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
TEXT_DATES = [
    (re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d\d)\b"), "dmy"),                       # 12.11.2026
    (re.compile(r"\b(20\d\d)-(\d{2})-(\d{2})\b"), "ymd"),                                     # 2026-11-12
    (re.compile(rf"\b(\d{{1,2}})\.?\s+(?:de\s+)?({MONTH_RE})\.?,?\s+(?:de\s+)?(20\d\d)\b", re.I), "d_month_y"),
    (re.compile(rf"\b({MONTH_RE})\.?\s+(\d{{1,2}}),?\s+(20\d\d)\b", re.I), "month_d_y"),       # November 12, 2026
]
META_DATE_KEYS = {"article:published_time", "og:published_time", "datepublished", "date", "dc.date",
                  "dc.date.issued", "pubdate", "publishdate", "publish_date", "parsely-pub-date", "sailthru.date"}
STOPWORDS = {
    "en": "the and of to in for with our is are we",
    "de": "der die das und für mit ist wir unsere eine nicht",
    "nl": "de het een en van voor met zijn wij onze",
    "es": "el la los las y de para con es nuestra",
    "fr": "le la les et des pour avec est nous notre",
    "pl": "i w na z do się jest oraz dla nasz",
}
#--------------------------------------------------------------#

def _today() -> date:
    return datetime.now(timezone.utc).date()

def _valid(d: date | None) -> date | None:
    """Dates outside 2000..tomorrow are misreads (copyright years, event dates far ahead)."""
    if not d or d.year < 2000 or d > _today() + timedelta(days=1):
        return None
    return d

def parse_date(text: str | None) -> date | None:
    """Any machine date (ISO, RFC 822 from feeds) -> date."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return _valid(datetime.fromisoformat(text.replace("Z", "+00:00")).date())
    except ValueError:
        pass
    m = re.match(r"(20\d\d)-(\d{2})-(\d{2})", text)
    if m:
        try:
            return _valid(date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            return None
    try:
        return _valid(parsedate_to_datetime(text).date())
    except (TypeError, ValueError, IndexError):
        return None

def text_date(text: str) -> date | None:
    """The first readable date in a piece of page text."""
    found = []
    for pattern, kind in TEXT_DATES:
        for m in pattern.finditer(text):
            try:
                if kind == "dmy":
                    d = date(int(m[3]), int(m[2]), int(m[1]))
                elif kind == "ymd":
                    d = date(int(m[1]), int(m[2]), int(m[3]))
                elif kind == "d_month_y":
                    d = date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
                else:
                    d = date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
            except (ValueError, KeyError):
                continue
            if _valid(d):
                found.append((m.start(), d))
                break
    return min(found)[1] if found else None
#--------------------------------------------------------------#

# A page's publish date and where it came from: (date, source) or (None, None)
def page_date(html: str, url: str, text: str) -> tuple[date | None, str | None]:
    for m in re.finditer(r"<meta\b[^>]*>", html[:200_000], re.I):
        tag = m.group(0)
        key = re.search(r"(?:property|name|itemprop)\s*=\s*[\"']([^\"']+)", tag, re.I)
        value = re.search(r"content\s*=\s*[\"']([^\"']+)", tag, re.I)
        if key and value and key.group(1).lower() in META_DATE_KEYS:
            d = parse_date(value.group(1))
            if d:
                return d, "meta"
    m = re.search(r"\"datePublished\"\s*:\s*\"([^\"]+)\"", html)
    if m and parse_date(m.group(1)):
        return parse_date(m.group(1)), "json-ld"
    m = re.search(r"<time\b[^>]*datetime\s*=\s*[\"']([^\"']+)", html, re.I)
    if m and parse_date(m.group(1)):
        return parse_date(m.group(1)), "time tag"
    m = re.search(r"/(20\d\d)[/-](\d{1,2})(?:[/-](\d{1,2}))?(?:/|-|$)", urlparse(url).path)
    if m:
        try:
            d = _valid(date(int(m[1]), int(m[2]), int(m[3] or 1)))
            if d:
                return d, "url"
        except ValueError:
            pass
    d = text_date(text[:2500])
    return (d, "text") if d else (None, None)

def page_lang(html: str, text: str) -> str | None:
    m = re.search(r"<html\b[^>]*\blang\s*=\s*[\"']?([a-zA-Z]{2})", html[:5000])
    if m:
        return m.group(1).lower()
    words = Counter(re.findall(r"\w+", text.lower()[:5000]))
    scores = {lang: sum(words[w] for w in ws.split()) for lang, ws in STOPWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 5 else None
#--------------------------------------------------------------#

def blocked(html: str) -> bool:
    """A bot check (Cloudflare and similar). We stop there: getting around it is not something we do."""
    head = html[:20000].lower()
    return ("cf-challenge" in head or "just a moment..." in head or "cf_chl_" in head
            or "attention required! | cloudflare" in head or "captcha-delivery" in head)

def _same_site(url: str, site: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and web.registrable(parsed.netloc) == site

def _article_like(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not path.endswith(FILE_ENDINGS) and not SKIP_WORDS.search(url) and path.count("/") <= 6
#--------------------------------------------------------------#

# Feeds: [{"url", "title", "date", "summary"}]
def _feed_items(xml: str) -> list[dict]:
    items = []
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", xml, re.S | re.I):
        def tag(name):
            m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.S | re.I)
            return unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        link = tag("link")
        if not link.startswith("http"):
            m = re.search(r"<link\b[^>]*href\s*=\s*[\"']([^\"']+)", block, re.I)
            link = m.group(1) if m else ""
        when = parse_date(tag("pubDate") or tag("published") or tag("updated") or tag("dc:date"))
        summary = re.sub(r"<[^>]+>", " ", tag("description") or tag("summary") or tag("content"))
        if link:
            items.append({"url": link, "title": re.sub(r"<[^>]+>", "", tag("title")), "date": when,
                          "summary": re.sub(r"\s+", " ", summary).strip()[:1500]})
    return items

def feeds(home_html: str, home_url: str) -> list[dict]:
    urls = re.findall(r"<link\b[^>]*type\s*=\s*[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", home_html, re.I)
    found = [urljoin(home_url, m.group(1)) for tag in urls
             if (m := re.search(r"href\s*=\s*[\"']([^\"']+)", tag, re.I))]
    base = f"{urlparse(home_url).scheme}://{urlparse(home_url).netloc}"
    tries = found or [base + p for p in FEED_PATHS[:4]]
    items = []
    for url in list(dict.fromkeys(tries))[:4]:
        page = web.fetch(url, any_type=True)
        if page and re.search(r"<(rss|feed)\b", page["html"][:2000], re.I):
            items += _feed_items(page["html"])
    return items
#--------------------------------------------------------------#

# Sitemap entries [(url, lastmod date or None)], news-like sitemaps first
def sitemap(home_url: str, limit_maps: int = 6) -> list[tuple[str, date | None]]:
    parsed = urlparse(home_url)
    maps = web.sitemaps(home_url) or [f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
                                      f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml"]
    seen, out = set(), []
    while maps and len(seen) < limit_maps:
        sm = maps.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        page = web.fetch(sm, any_type=True)
        if not page:
            continue
        body = page["html"]
        if "<sitemapindex" in body:
            children = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
            children.sort(key=lambda u: (not NEWS_WORDS.search(u) and "post" not in u.lower(), u))
            maps = children[:limit_maps] + maps
            continue
        for block in re.findall(r"<url>(.*?)</url>", body, re.S):
            loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
            mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block)
            if loc:
                out.append((unescape(loc.group(1)), parse_date(mod.group(1)) if mod else None))
        if len(out) > 20000:
            break
    return out
#--------------------------------------------------------------#

# Candidate pages, best first: [{"url", "source", "date" (may be None), "title", "summary"}]
def candidates(home: dict, site: str, since: date) -> list[dict]:
    home_url, home_html = home["url"], home["html"]
    out, seen = [], set()

    def add(url, source, when=None, title="", summary=""):
        url = url.split("#")[0]
        if url in seen or not _same_site(url, site) or not _article_like(url):
            return
        if when and when < since:
            return
        seen.add(url)
        out.append({"url": url, "source": source, "date": when, "title": title, "summary": summary})

    for item in sorted(feeds(home_html, home_url), key=lambda i: i["date"] or date.min, reverse=True):
        if item["date"]:
            add(item["url"], "feed", item["date"], item["title"], item["summary"])
    entries = sitemap(home_url)
    dated = sorted(((u, d) for u, d in entries if d and d >= since), key=lambda x: x[1], reverse=True)
    for url, when in dated:
        if NEWS_WORDS.search(urlparse(url).path):
            add(url, "sitemap", when)
    listing_pages = [l for l in web.read_html(home_html, home_url)["links"]
                     if _same_site(l, site) and NEWS_WORDS.search(urlparse(l).path)
                     and urlparse(l).path.strip("/").count("/") <= 2 and not SKIP_WORDS.search(l)]
    for listing in list(dict.fromkeys(listing_pages))[:2]:
        page = web.fetch(listing)
        if not page:
            continue
        base_path = urlparse(page["url"]).path.rstrip("/")
        for link in web.read_html(page["html"], page["url"])["links"]:
            path = urlparse(link).path.rstrip("/")
            if path.startswith(base_path + "/") or NEWS_WORDS.search(path):
                if path != base_path:
                    add(link, "news page")
    for url, when in dated:                                   # other recently changed pages last
        add(url, "sitemap", when)
    return out
#--------------------------------------------------------------#

# Lines repeated across a site's pages (menus, footers) removed from each page's text
def strip_repeats(texts: list[str]) -> list[str]:
    lines = [set(l.strip() for l in t.splitlines() if l.strip()) for t in texts]
    counts = Counter(l for s in lines for l in s)
    limit = max(2, int(0.4 * len(texts) + 0.999))
    return ["\n".join(l for l in t.splitlines() if l.strip() and counts[l.strip()] < limit) for t in texts]
#--------------------------------------------------------------#

# Reads one website: returns {"status", "home_url", "pages": [...]} (pages: url, source, title,
# published_at, date_source, lang, text)
def read_site(home_url: str, since: date, max_pages: int, skip_urls: set[str] = frozenset()) -> dict:
    home = web.fetch(home_url)
    if not home:
        return {"status": "unreachable", "home_url": home_url, "pages": []}
    if blocked(home["html"]):
        return {"status": "blocked", "home_url": home_url, "pages": []}
    site = web.registrable(urlparse(home["url"]).netloc)
    raw = []
    for cand in candidates(home, site, since):
        if len(raw) >= max_pages:
            break
        if cand["url"] in skip_urls:
            continue
        page = web.fetch(cand["url"])
        if not page or blocked(page["html"]):
            if cand["source"] == "feed" and cand["summary"]:          # the feed's own text will do
                raw.append((cand, None, cand["summary"]))
            continue
        read = web.read_html(page["html"], page["url"])
        cand = {**cand, "url": page["url"], "title": cand["title"] or read["title"]}
        raw.append((cand, page["html"], read["text"]))
    home_text = web.read_html(home["html"], home["url"])["text"]
    cleaned = strip_repeats([home_text] + [t for _, _, t in raw])[1:]

    pages = []
    for (cand, html, text), clean in zip(raw, cleaned):
        when, source = (page_date(html, cand["url"], text) if html else (None, None))
        trusted = cand["source"] == "feed" or (cand["source"] == "sitemap" and NEWS_WORDS.search(urlparse(cand["url"]).path))
        if cand["date"] and (cand["source"] == "feed" or (not when and trusted)):   # a product page's "last changed" isn't news
            when, source = cand["date"], cand["source"]
        if not when or when < since:
            continue                                                  # undated or too old: not an update
        heading = next((l.strip() for l in clean.splitlines() if len(l.strip()) >= 8), "")   # no <title>: first real line
        pages.append({"url": cand["url"], "source": cand["source"], "title": (cand["title"] or heading).strip()[:300],
                      "published_at": when.isoformat(), "date_source": source,
                      "lang": page_lang(html or "", text), "text": clean[:6000]})
    return {"status": "ok", "home_url": home["url"], "pages": pages}
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
