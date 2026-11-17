#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/crawler/site.py
# Purpose: read a company's public website for contact evidence. Free: no API, no credits.
#            1. picks the useful pages (Impressum/imprint, contact, team/about, press, careers) from the
#               homepage links and the sitemap; at most MAX_PAGES per site
#            2. collects every email address, and the person's name next to it when the address
#               really matches that name (so "m.weber@" next to "Michael Weber" -> format f.last)
#            3. collects named people with a role: legal representatives from the Impressum
#               ("Geschäftsführer: ...") and names next to a target role on team/about pages
#          Results are saved in site_crawls / site_emails (shared by all clients) and reused for a day.
#--------------------------------------------------------------#

# Imports libraries
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from job_alerts.crawler import web
from job_alerts.emails.base import split_name
from job_alerts.emails.patterns import detect_format
#--------------------------------------------------------------#

# Global variables
MAX_PAGES = 15
REUSE_HOURS = 24
PAGE_GROUPS = [            # (group, words in the URL path, pages kept) ... most useful first
    ("legal", ["impressum", "imprint", "legal-notice", "legal_notice", "legalnotice", "mentions-legales",
               "aviso-legal", "colofon", "nota-prawna", "informacje-prawne", "stopka-redakcyjna"], 2),
    ("contact", ["kontakt", "contact", "contacto", "contatti", "kontakty", "ansprechpartner"], 3),
    ("team", ["team", "management", "leadership", "geschaeftsfuehrung", "geschaftsfuhrung", "vorstand",
              "about", "ueber-uns", "uber-uns", "unternehmen", "company", "wir-ueber-uns", "over-ons",
              "quienes-somos", "o-nas", "o-firmie", "people", "founders", "board"], 5),
    ("press", ["presse", "press", "newsroom", "media", "medien", "news"], 2),
    ("careers", ["karriere", "careers", "career", "jobs", "werken-bij", "werkenbij", "empleo", "kariera"], 2),
]
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".doc", ".docx", ".xls", ".xlsx",
                   ".mp4", ".mp3", ".webp", ".ics", ".xml")
GENERIC_LOCALS = {"info", "kontakt", "contact", "office", "sales", "vertrieb", "hr", "jobs", "job", "karriere",
                  "bewerbung", "bewerbungen", "career", "careers", "recruiting", "press", "presse", "marketing",
                  "support", "service", "datenschutz", "privacy", "dpo", "noreply", "no-reply", "mail", "hello",
                  "hallo", "team", "admin", "webmaster", "buchhaltung", "accounting", "invoice", "invoices",
                  "rechnung", "rechnungen", "einkauf", "purchasing", "empfang", "zentrale", "post", "postmaster",
                  "abuse", "legal", "compliance", "it", "media", "news", "newsletter", "order", "orders",
                  "bestellung", "anfrage", "anfragen", "help", "feedback", "inquiries", "enquiries", "welcome",
                  "contacto", "kontakty", "biuro", "recepcja", "hola", "hallo", "investor", "ir", "events"}
# Labels before the legal representatives' names in an Impressum / legal notice
LEGAL_LABEL = re.compile(
    r"(gesch[äa]ftsf[üu]hr(?:er(?:in)?|ung|ende[rn]?(?: gesellschafter(?:in)?)?)|vertretungsberechtigte[rn]?"
    r"(?: gesch[äa]ftsf[üu]hrer(?:in)?)?|vertreten durch(?: die gesch[äa]ftsf[üu]hrer)?|vorstand(?:svorsitzende[r]?)?"
    r"|inhaber(?:in)?|managing directors?|chief executive officer|ceo|directors?|bestuurder[s]?|directie"
    r"|prezes zarz[ąa]du|zarz[ąa]d|administrador(?:es)?|consejero delegado)\s*[:\-–]?\s*(.*)",
    re.IGNORECASE)
_UP = "A-ZÄÖÜÉÁÍÓÚŁŚŻ"
_LO = "a-zäöüßéèáíóúñłśżćąęńő'"
_WORD = rf"[{_UP}][{_LO}]+(?:-[{_UP}][{_LO}]+)?"            # "Weber", "Anna-Lena"
NAME = re.compile(rf"(?:(?:Dr|Prof|Dipl|Ing|Mag)\.?(?:-\w+\.?)?[ \t]+)*"   # titles are dropped
                  rf"({_WORD}(?:[ \t]+(?:von|van|de|der|den|zu|da|di|del|la)){{0,2}}(?:[ \t]+{_WORD}){{1,2}})")
NOT_NAME_WORDS = {"gmbh", "kg", "ag", "co", "ltd", "inc", "telefon", "phone", "fax", "email", "e-mail", "mail",
                  "straße", "strasse", "str", "platz", "weg", "registergericht", "amtsgericht", "handelsregister",
                  "impressum", "imprint", "kontakt", "contact", "head", "chief", "officer", "director", "manager",
                  "management", "supply", "chain", "data", "sales", "marketing", "team", "unternehmen", "company",
                  "germany", "deutschland", "sitz", "ust", "umsatzsteuer", "vat", "office", "group", "holding",
                  "board", "member", "members", "vorstand", "aufsichtsrat", "vorsitzender", "vorsitz", "geschäftsführer",
                  "managing", "partner", "partners", "solutions", "services", "digital", "global", "international",
                  "privacy", "policy", "datenschutz", "cookie", "cookies", "news", "presse", "press", "career",
                  "karriere", "jobs", "about", "home", "startseite", "read", "more", "mehr", "lesen", "unsere",
                  "our", "the", "und", "and", "für", "for", "mit", "with", "berlin", "münchen", "hamburg",
                  "frankfurt", "köln", "stuttgart", "düsseldorf", "wien", "zürich", "europe", "europa", "ihr",
                  "ihre", "your", "dein", "deine", "herr", "frau", "mr", "mrs", "ms", "dr", "prof", "seit", "since",
                  "auf", "nachfrage", "bitte", "hier", "alle", "north", "south", "america", "american", "asia",
                  "führungskräfte", "standort", "standorte", "abteilung", "bereich", "kunden", "service"}
GENERIC_ROLES = ["geschäftsführer", "geschäftsführerin", "geschäftsführung", "managing director", "ceo",
                 "chief executive", "founder", "co-founder", "gründer", "inhaber", "owner", "vorstand",
                 "president", "cto", "cio", "coo", "cmo", "chief"]
#--------------------------------------------------------------#

def _now() -> datetime:
    return datetime.now(timezone.utc)
#--------------------------------------------------------------#

# "Michael Weber" -> True; "Supply Chain" -> False
def looks_like_name(name: str) -> bool:
    words = [w.strip(".,").lower() for w in name.split()]
    if len(words) < 2 or len(words) > 4:
        return False
    return not any(w in NOT_NAME_WORDS for w in words) and all(len(w) >= 2 for w in words)
#--------------------------------------------------------------#

def is_generic(email: str) -> bool:
    local, domain = email.lower().split("@", 1)
    return local in GENERIC_LOCALS or re.sub(r"[\d._-]+$", "", local) in GENERIC_LOCALS \
        or local == domain.split(".")[0] or not re.search(r"[a-z]{2}", local)   # bitzer@bitzer.de, t500@
#--------------------------------------------------------------#

# All name-like phrases in a text (and the two-word names inside three-word ones)
def names_in(text: str) -> list[str]:
    names = []
    for m in NAME.finditer(text):
        words = m.group(1).split()
        names.append(m.group(1))
        if len(words) == 3:                          # "Anna Maria Weber" -> also the two-word names inside
            names += [f"{words[0]} {words[2]}", f"{words[1]} {words[2]}", f"{words[0]} {words[1]}"]
    return list(dict.fromkeys(names))

# The name that matches an email address: (name, format) or (None, None). Looks next to the address
# first, then anywhere in the given names (e.g. "Stefanie Holst" further up a press page).
def name_for_email(text: str, email: str, position: int, more_names: list[str] | None = None
                   ) -> tuple[str | None, str | None]:
    if position < 0:
        position = text.lower().find(email)
    near = names_in(text[max(0, position - 200): position + 100]) if position >= 0 else []
    for name in near + [n for n in (more_names or []) if n not in near]:
        if not looks_like_name(name):
            continue
        fmt = detect_format(name, email)
        if fmt and fmt not in ("first", "last"):     # a bare first or last name could be anyone
            return name, fmt
    return None, None
#--------------------------------------------------------------#

# Legal representatives from an Impressum: [(name, role)]
def legal_people(text: str) -> list[tuple[str, str]]:
    out, lines = [], text.split("\n")
    for i, line in enumerate(lines):
        m = LEGAL_LABEL.search(line)
        if not m or len(line) > 300:
            continue
        rest = m.group(2).strip()
        if not rest and i + 1 < len(lines):          # label on its own line, names on the next one
            rest = lines[i + 1]
        role = re.sub(r"(?i)^vertreten durch( die)?\s*", "", m.group(1).strip()) or "Geschäftsführer"
        role = "Geschäftsführer" if re.search(r"(?i)gesch[äa]ftsf[üu]hr", role) else role.title()
        for part in re.split(r",|;|/|\bund\b|\band\b|&|\bi\b|\by\b|\ben\b", rest):
            nm = NAME.search(part.strip())
            if nm and looks_like_name(nm.group(1)) and (nm.group(1), role) not in out:
                out.append((nm.group(1), role))
    return out[:6]
#--------------------------------------------------------------#

# Names standing next to one of the roles (e.g. on a team page): [(name, role)]
def role_people(text: str, roles: list[str]) -> list[tuple[str, str]]:
    out, low = [], text.lower()
    for role in roles:
        r = role.lower().strip()
        if len(r) < 3:
            continue
        for m in re.finditer(rf"(?<![a-zäöü]){re.escape(r)}(?![a-zäöü])", low):
            before = text[max(0, m.start() - 80): m.start()]
            after = text[m.end(): m.end() + 60]
            names = [n.group(1) for n in NAME.finditer(before)][-1:] + [n.group(1) for n in NAME.finditer(after)][:1]
            for name in names:
                if looks_like_name(name) and all(name != n for n, _ in out):
                    out.append((name, role))
                    break
            if len(out) >= 10:
                return out
    return out
#--------------------------------------------------------------#

# Which group a URL belongs to, or None
def page_group(url: str, site: str) -> tuple[int, str] | None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or web.registrable(parsed.netloc) != site:
        return None
    path = parsed.path.lower()
    if path.endswith(SKIP_EXTENSIONS) or path.count("/") > 4:
        return None
    for rank, (group, words, _) in enumerate(PAGE_GROUPS):
        if any(w in path for w in words):
            return rank, group
    return None
#--------------------------------------------------------------#

# URLs listed in the site's sitemap(s); at most a few thousand
def sitemap_urls(home_url: str) -> list[str]:
    parsed = urlparse(home_url)
    maps = web.sitemaps(home_url) or [f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"]
    urls, seen = [], set()
    while maps and len(seen) < 6:
        sm = maps.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        page = web.fetch(sm, any_type=True)
        if not page:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", page["html"])
        if "<sitemapindex" in page["html"]:
            maps += [l for l in locs if not re.search(r"product|post-|image|video|blog", l)][:4]
        else:
            urls += locs
        if len(urls) > 5000:
            break
    return urls
#--------------------------------------------------------------#

# Crawl one website (or reuse a crawl from the last REUSE_HOURS). roles: target roles from the config.
def crawl(conn, domain: str, roles: list[str]) -> dict:
    row = conn.execute("SELECT * FROM site_crawls WHERE domain = ?", (domain,)).fetchone()
    if row and row["crawled_at"] and \
            datetime.fromisoformat(row["crawled_at"]) > _now() - timedelta(hours=REUSE_HOURS):
        return _load(conn, domain, row)

    home = web.fetch(f"https://{domain}/") or web.fetch(f"https://www.{domain}/") or web.fetch(f"http://{domain}/")
    if not home:
        status = "blocked" if not web.allowed(f"https://{domain}/") else "unreachable"
        _save(conn, domain, None, 0, [], [], status)
        return {"status": status, "home_url": None, "emails": [], "people": [], "text": ""}

    site = web.registrable(urlparse(home["url"]).netloc)
    pages = [home]
    first = web.read_html(home["html"], home["url"])
    pool = {u: page_group(u, site) for u in first["links"] + sitemap_urls(home["url"])}
    done, kept = {home["url"].rstrip("/")}, {g: 0 for g, _, _ in PAGE_GROUPS}
    limits = {g: n for g, _, n in PAGE_GROUPS}
    while len(pages) < MAX_PAGES:
        todo = sorted(((grp, len(u), u) for u, grp in pool.items()
                       if grp and u.rstrip("/") not in done and kept[grp[1]] < limits[grp[1]]))
        if not todo:
            break
        (rank, group), _, url = todo[0]
        done.add(url.rstrip("/"))
        page = web.fetch(url)
        if not page:
            continue
        kept[group] += 1
        page["group"] = group
        pages.append(page)
        if group in ("legal", "contact", "team"):    # e.g. the team page linked from "about"
            for link in web.read_html(page["html"], page["url"])["links"]:
                if link not in pool:
                    pool[link] = page_group(link, site)
    #--------------------------------------------------------------#

    texts = []
    for page in pages:
        read = web.read_html(page["html"], page["url"])
        texts.append((page, read, web.unspell(read["text"])))
    site_names = list(dict.fromkeys(n for _, _, t in texts for n in names_in(t[:60000]) if looks_like_name(n)))

    emails, people, all_text = {}, [], []
    for page, read, text in texts:
        all_text.append(f"{read['title']}\n{read['site_name']}\n{text}")
        found = web.find_emails(text) + [(e.lower(), -1) for e in read["extra_emails"] if "@" in e]
        for email, pos in found:
            name, fmt = (None, None) if is_generic(email) else name_for_email(text, email, pos, site_names)
            if email not in emails or (name and not emails[email]["name"]):
                emails[email] = {"email": email, "name": name, "email_format": fmt,
                                 "is_generic": int(is_generic(email)), "source_url": page["url"]}
        group = page.get("group", "home")
        found_people = legal_people(text) if group in ("legal", "contact", "home") else []
        found_people = [(n, r, "legal") for n, r in found_people]
        if group in ("team", "legal", "home", "contact", "press"):   # only the client's target roles here:
            found_people += [(n, r, "role") for n, r in role_people(text, roles)]   # executives come from the Impressum
        for name, role, kind in found_people:
            if all(p["name"] != name for p in people):
                people.append({"name": name, "role": role, "kind": kind, "source_url": page["url"]})
    for e in emails.values():                        # a named address is a person too
        if e["name"] and all(p["name"] != e["name"] for p in people):
            people.append({"name": e["name"], "role": None, "kind": "email", "source_url": e["source_url"]})

    _save(conn, domain, home["url"], len(pages), list(emails.values()), people, "ok")
    return {"status": "ok", "home_url": home["url"], "emails": list(emails.values()), "people": people,
            "text": "\n".join(all_text)[:200_000], "pages": len(pages)}
#--------------------------------------------------------------#

def _save(conn, domain, home_url, pages, emails, people, status) -> None:
    now = _now().isoformat()
    conn.execute("INSERT INTO site_crawls (domain, home_url, pages, emails_found, people, status, crawled_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (domain) DO UPDATE SET home_url = excluded.home_url, "
                 "pages = excluded.pages, emails_found = excluded.emails_found, people = excluded.people, "
                 "status = excluded.status, crawled_at = excluded.crawled_at",
                 (domain, home_url, pages, len(emails), json.dumps(people, ensure_ascii=False), status, now))
    for e in emails:
        conn.execute("INSERT INTO site_emails (domain, email, name, email_format, is_generic, source_url, found_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (domain, email) DO UPDATE SET "
                     "name = COALESCE(excluded.name, site_emails.name), "
                     "email_format = COALESCE(excluded.email_format, site_emails.email_format), "
                     "source_url = excluded.source_url, found_at = excluded.found_at",
                     (domain, e["email"], e["name"], e["email_format"], e["is_generic"], e["source_url"], now))
    conn.commit()

def _load(conn, domain, row) -> dict:
    emails = [dict(r) for r in conn.execute("SELECT email, name, email_format, is_generic, source_url "
                                            "FROM site_emails WHERE domain = ?", (domain,))]
    return {"status": row["status"], "home_url": row["home_url"], "emails": emails,
            "people": json.loads(row["people"] or "[]"), "text": "", "pages": row["pages"]}
#--------------------------------------------------------------#

# People on the site worth an email, best first: target roles, then legal representatives
def ranked_people(people: list[dict], roles: list[str]) -> list[dict]:
    def rank(p):
        role = (p.get("role") or "").lower()
        for i, r in enumerate(roles):
            if role and (r.lower() in role or role in r.lower()):
                return i
        if p["kind"] == "legal" or any(g in role for g in GENERIC_ROLES):
            return len(roles) + 1
        return None
    ranked = sorted((rank(p), i) for i, p in enumerate(people)
                    if rank(p) is not None and all(split_name(p["name"])))
    return [people[i] for _, i in ranked]
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
