#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/crawler/web.py
# Purpose: polite fetching of public web pages, and reading them. Free: no API, no credits.
#            - follows each site's robots.txt and waits between requests to the same site
#            - only HTML pages, at most MAX_BYTES each
#            - turns HTML into plain text and links, finds email addresses (incl. "name(at)firma.de"
#              and Cloudflare-hidden addresses), and checks domains with public DNS (dns.google)
#--------------------------------------------------------------#

# Imports libraries
import html
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
#--------------------------------------------------------------#

# Global variables
USER_AGENT = "Mozilla/5.0 (compatible; job-alerts-enrich/1.0; company contact page reader)"
BOT_NAME = "job-alerts-enrich"
TIMEOUT = 15
MAX_BYTES = 2_000_000
DELAY_SECONDS = 1.5                       # pause between two requests to the same site
EMAIL = re.compile(r"(?<![\w.+-])([a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24})(?![\w-])",
                   re.IGNORECASE)
AT_SPELLED = re.compile(r"\s*(?:\(at\)|\[at\]|\{at\}|\(@\)|\[@\])\s*", re.IGNORECASE)
DOT_SPELLED = re.compile(r"\s*(?:\(dot\)|\[dot\]|\{dot\}|\(punkt\)|\[punkt\])\s*", re.IGNORECASE)
NOT_EMAIL_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
TWO_PART_SUFFIXES = {"co.uk", "org.uk", "ac.uk", "com.au", "co.in", "net.in", "org.in", "com.sg", "co.za",
                     "com.br", "co.jp", "com.tr", "com.pl", "co.nz", "com.mx", "com.cn", "com.hk", "co.il"}
_last_request: dict[str, float] = {}      # host -> time of the last request (politeness delay)
_robots: dict[str, RobotFileParser | None] = {}
_client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "en,de;q=0.8"},
                       timeout=TIMEOUT, follow_redirects=True)
#--------------------------------------------------------------#

# "jobs.example.co.uk" -> "example.co.uk"
def registrable(host: str) -> str:
    host = (host or "").lower().split(":")[0].strip(".").removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host

def host_of(url: str) -> str:
    return urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
#--------------------------------------------------------------#

def _wait_for(host: str) -> None:
    gap = time.time() - _last_request.get(host, 0)
    if gap < DELAY_SECONDS:
        time.sleep(DELAY_SECONDS - gap)
    _last_request[host] = time.time()
#--------------------------------------------------------------#

# robots.txt of a site (read once per run); None = no rules found, everything allowed
def _robots_for(url: str) -> RobotFileParser | None:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base in _robots:
        return _robots[base]
    rules = None
    try:
        _wait_for(parsed.netloc)
        resp = _client.get(base + "/robots.txt")
        if resp.status_code == 200 and "text" in resp.headers.get("content-type", "text"):
            rules = RobotFileParser()
            rules.parse(resp.text.splitlines())
    except httpx.HTTPError:
        pass
    _robots[base] = rules
    return rules

def allowed(url: str) -> bool:
    rules = _robots_for(url)
    return rules is None or rules.can_fetch(BOT_NAME, url)

def sitemaps(url: str) -> list[str]:
    rules = _robots_for(url)
    return list(rules.site_maps() or []) if rules else []
#--------------------------------------------------------------#

# Fetch one page politely. Returns {"url": final url, "html": text} or None (blocked, not HTML, error).
def fetch(url: str, check_robots: bool = True, any_type: bool = False) -> dict | None:
    if check_robots and not allowed(url):
        return None
    try:
        _wait_for(urlparse(url).netloc)
        resp = _client.get(url)
    except (httpx.HTTPError, ValueError):
        return None
    kind = resp.headers.get("content-type", "")
    if resp.status_code != 200 or (not any_type and "html" not in kind and "xml" not in kind):
        return None
    return {"url": str(resp.url), "html": resp.text[:MAX_BYTES]}
#--------------------------------------------------------------#

# HTML -> visible text (one line per block), links, title and Cloudflare-hidden emails
class _Reader(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "section",
              "article", "footer", "header", "address", "dd", "dt", "table", "ul", "ol"}
    SKIP = {"script", "style", "noscript", "svg", "template"}
    INLINE_GAP = {"a", "span", "button", "label", "img", "strong", "small", "b", "em", "i"}  # kept apart by a space

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden_emails = [], [], []
        self.title, self.site_name, self._skip, self._in_title = "", "", 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCKS:
            self.parts.append("\n")
        elif tag in self.INLINE_GAP:
            self.parts.append(" ")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "meta" and (a.get("property") == "og:site_name") and a.get("content"):
            self.site_name = a["content"]
        if a.get("data-cfemail"):
            self.hidden_emails.append(decode_cloudflare(a["data-cfemail"]))
        href = a.get("href") or ""
        if "/cdn-cgi/l/email-protection#" in href:
            self.hidden_emails.append(decode_cloudflare(href.split("#", 1)[1]))

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCKS:
            self.parts.append("\n")
        elif tag in self.INLINE_GAP:
            self.parts.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)

def decode_cloudflare(code: str) -> str:
    try:
        key = int(code[:2], 16)
        return "".join(chr(int(code[i:i + 2], 16) ^ key) for i in range(2, len(code), 2))
    except ValueError:
        return ""

def read_html(page_html: str, base_url: str) -> dict:
    reader = _Reader()
    try:
        reader.feed(page_html)
    except Exception:
        pass
    text = re.sub(r"[ \t\r\f\v\xa0]+", " ", "".join(reader.parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    links = []
    for href in reader.links:
        href = html.unescape(href.strip())
        if href.lower().startswith("mailto:"):
            reader.hidden_emails.append(href[7:].split("?")[0])
            continue
        if href.startswith(("javascript:", "tel:", "#")):
            continue
        links.append(urljoin(base_url, href).split("#")[0])
    return {"text": text, "links": list(dict.fromkeys(links)), "title": reader.title.strip(),
            "site_name": reader.site_name.strip(), "extra_emails": [e for e in reader.hidden_emails if e]}
#--------------------------------------------------------------#

# Spelled-out addresses back to normal: "info(at)firma(dot)de" -> "info@firma.de"
def unspell(text: str) -> str:
    return DOT_SPELLED.sub(".", AT_SPELLED.sub("@", text))

# All email addresses in a text (run unspell first): [(email, position in that text)]
def find_emails(text: str) -> list[tuple[str, int]]:
    out = []
    for m in EMAIL.finditer(text):
        email = m.group(1).lower().strip(".")
        if email.endswith(NOT_EMAIL_ENDINGS) or "@2x" in email or email.startswith(("example@", "name@")):
            continue
        out.append((email, m.start()))
    return out
#--------------------------------------------------------------#

# Public DNS (Google DNS over HTTPS): record values for a name, e.g. ("firma.de", "MX")
def dns(name: str, kind: str) -> list[str]:
    try:
        resp = httpx.get("https://dns.google/resolve", params={"name": name, "type": kind}, timeout=10)
        code = {"A": 1, "MX": 15, "CNAME": 5}.get(kind)
        return [a.get("data", "") for a in resp.json().get("Answer", []) if a.get("type") == code]
    except Exception:
        return []
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
