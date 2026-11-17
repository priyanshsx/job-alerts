#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/crawler/domains.py
# Purpose: find a lead's company website, free methods first:
#            1. job link     the posting is on the company's own site (jobs.firma.de)
#            2. job text     a website or email address in the job description
#            3. job page     the company link on an ATS page (Greenhouse, Lever, Workable ...)
#            4. guess        company name + the country's usual endings (.de, .com ...), checked in DNS
#            5. search       the existing find_domain (one Unoblox search + LLM): the only paid step
#          A domain is "confirmed" only when the website carries the company's name. Otherwise it is
#          "uncertain" and no emails are written (a verified email at the wrong company is worse
#          than none). A domain typed in the sheet always wins ("manual").
#--------------------------------------------------------------#

# Imports libraries
import re
from urllib.parse import urlparse
from job_alerts.core.names import normalize_name
from job_alerts.crawler import web
#--------------------------------------------------------------#

# Global variables
JOB_HOSTS = ("linkedin.", "arbeitsagentur.", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
             "personio.", "smartrecruiters.", "recruitee.com", "teamtailor.com", "join.com", "stepstone.",
             "indeed.", "glassdoor.", "gute-jobs.", "finest-jobs.", "persy.jobs", "heyjobs.", "reddit.",
             "x.com", "twitter.", "xing.", "kununu.", "monster.", "jobs.ch", "karriere.at", "softgarden.",
             "successfactors.", "myworkdayjobs.", "workday.", "bamboohr.", "breezy.hr", "jobvite.", "icims.",
             "taleo.", "wellfound.", "angel.co", "instahyre.", "naukri.", "cutshort.", "iimjobs.", "foundit.",
             "remoteok.", "weworkremotely.", "remotive.", "ycombinator.", "jobs.lever", "facebook.",
             "instagram.", "youtube.", "google.", "wikipedia.", "adzuna.", "jooble.", "stellenanzeigen.",
             "jobware.", "experteer.", "meinestadt.", "yourfirm.", "jobs.de", "kimeta.", "jobboerse.",
             "talent.com", "simplyhired.", "ziprecruiter.", "hiring.cafe", "otta.", "welcometothejungle.",
             "github.", "medium.com", "substack.com", "t.co", "bit.ly", "lnkd.in", "goo.gl", "apple.com",
             "microsoft.com", "w3.org", "schema.org", "cloudflare.", "googletagmanager.", "gstatic.",
             "hotjar.", "cookiebot.", "usercentrics.", "onetrust.", "jsdelivr.", "unpkg.", "fonts.",
             "northdata.", "crunchbase.", "bloomberg.", "dnb.com", "zoominfo.", "kununu.", "trustpilot.")
MAIL_PROVIDERS = ("gmail.", "googlemail.", "outlook.", "hotmail.", "live.", "yahoo.", "gmx.", "web.de",
                  "t-online.", "icloud.", "aol.", "proton", "freenet.", "arcor.", "mail.ru", "yandex.")
ATS_SLUGS = [r"(?:job-boards|boards)\.(?:eu\.)?greenhouse\.io/([^/?#]+)", r"jobs\.(?:eu\.)?lever\.co/([^/?#]+)",
             r"jobs\.ashbyhq\.com/([^/?#]+)", r"apply\.workable\.com/([^/?#]+)",
             r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)", r"([a-z0-9-]+)\.recruitee\.com",
             r"([a-z0-9-]+)\.teamtailor\.com", r"([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com",
             r"join\.com/companies/([^/?#]+)", r"([a-z0-9-]+)\.bamboohr\.com", r"([a-z0-9-]+)\.breezy\.hr",
             r"jobs\.smartrecruiters\.com/([^/?#]+)"]
ATS_PAGES = ("greenhouse.io", "lever.co", "workable.com", "personio.", "recruitee.com", "teamtailor.com",
             "smartrecruiters.", "join.com", "bamboohr.com", "breezy.hr", "ashbyhq.com")
COUNTRY_ENDINGS = {"DE": ["de", "com"], "AT": ["at", "com", "de"], "CH": ["ch", "com", "de"],
                   "NL": ["nl", "com", "eu"], "BE": ["be", "com", "eu"], "ES": ["es", "com"],
                   "PL": ["pl", "com", "eu"], "HU": ["hu", "com"], "CZ": ["cz", "com"], "FR": ["fr", "com"],
                   "IT": ["it", "com"], "IN": ["com", "in", "co.in", "io"], "SG": ["com", "sg", "com.sg", "io"],
                   "GB": ["co.uk", "com", "io"], "UK": ["co.uk", "com", "io"], "US": ["com", "io", "co"],
                   "AE": ["com", "ae"], "": ["com", "io", "de", "co", "ai"]}
NOT_DISTINCTIVE = {"the", "und", "and", "of", "group", "gruppe", "holding", "international", "deutschland",
                   "germany", "india", "europe", "pvt", "private", "limited", "corp", "corporation", "company",
                   "inc", "llp"}
GENERIC_FIRST = {"stadtwerke", "deutsche", "deutscher", "bank", "sparkasse", "volksbank", "raiffeisenbank",
                 "klinikum", "universitaet", "hochschule", "landkreis", "stadt", "gemeinde", "first", "global",
                 "digital", "smart", "data", "tech", "energy", "green", "euro", "service", "services", "auto",
                 "capital", "media", "ventures", "consulting", "software", "solutions", "systems", "net", "web"}
PARKED = ("domain is for sale", "domain for sale", "buy this domain", "diese domain kaufen",
          "domain kann gekauft werden", "parked free", "sedo domain", "this domain is parked",
          "hugedomains", "dan.com", "afternic")
#--------------------------------------------------------------#

def _plain(text: str) -> str:
    """lower case, umlauts spelled out, a-z and 0-9 only"""
    t = (text or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def name_tokens(company: str) -> list[str]:
    return [t for t in normalize_name(company).split() if t not in NOT_DISTINCTIVE and len(t) >= 2][:4]

def is_job_host(host: str) -> bool:
    return any(h in host for h in JOB_HOSTS)
#--------------------------------------------------------------#

# Does this website belong to the company? ("confirmed", page text) / ("uncertain", reason)
def check_domain(domain: str, company: str) -> tuple[str, str]:
    tokens = name_tokens(company)
    label = _plain(domain.split(".")[0]).replace(" ", "")
    if not tokens:
        return "uncertain", "no company name to compare"
    page = web.fetch(f"https://{domain}/") or web.fetch(f"https://www.{domain}/") or web.fetch(f"http://{domain}/")
    if not page:
        if label == "".join(tokens) and web.dns(domain, "MX"):   # site blocks us, but the domain is the exact name
            return "confirmed", "domain is the company name (site not readable)"
        return "uncertain", "site not reachable or not allowed by robots.txt"
    read = web.read_html(page["html"], page["url"])
    text = f"{read['title']} {read['site_name']} {read['text'][:30000]}"
    if any(p in text.lower() for p in PARKED) or len(read["text"]) < 40 and not read["title"]:
        return "uncertain", "parked or empty page"
    final = web.registrable(urlparse(page["url"]).netloc)
    if final != domain and is_job_host(final):
        return "uncertain", f"redirects to {final}"
    plain = f" {_plain(text)} "
    compact = plain.replace(" ", "")
    if "".join(tokens) in compact or all(f" {t} " in plain for t in tokens):
        return "confirmed", final
    # The brand alone: "Liebherr-Hausgeräte Ochsenhausen" on liebherr.com, with "Liebherr" in the page title
    brand = tokens[0]
    if len(tokens) > 1 and len(brand) >= 4 and brand not in GENERIC_FIRST and label == brand \
            and f" {brand} " in f" {_plain(read['title'] + ' ' + read['site_name'])} ":
        return "confirmed", final
    # Imprint pages carry the full legal name; try one if the homepage didn't
    imprint = next((l for l in read["links"] if re.search(r"impressum|imprint|legal|about|ueber-uns", l.lower())
                    and web.registrable(urlparse(l).netloc) == final), None)
    if imprint:
        extra = web.fetch(imprint)
        if extra:
            plain2 = f" {_plain(web.read_html(extra['html'], extra['url'])['text'])} "
            if "".join(tokens) in plain2.replace(" ", "") or all(f" {t} " in plain2 for t in tokens):
                return "confirmed", final
    return "uncertain", "company name not found on the site"
#--------------------------------------------------------------#

# Domains named in the lead's job links: ([(domain, source)], [ATS slugs], [ATS page urls])
def _from_links(links: str) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    out, slugs, ats = [], [], []
    for url in re.findall(r"https?://[^\s,;]+", links or ""):
        host = urlparse(url).netloc.lower()
        for pat in ATS_SLUGS:
            m = re.search(pat, url.lower())
            if m:
                slugs.append(m.group(1))
        if any(a in host for a in ATS_PAGES):
            ats.append(url)
        elif host and not is_job_host(host):
            out.append((web.registrable(host), "job link"))
    return out, slugs, ats

# Websites and email domains written in the job descriptions
def _from_descriptions(conn, client_id: int, key: str) -> list[tuple[str, str]]:
    out = []
    ids = [r["id"] for r in conn.execute("SELECT id, company_name FROM job_postings WHERE client_id = ?",
                                         (client_id,)) if normalize_name(r["company_name"]) == key]
    for row in conn.execute(f"SELECT description FROM job_postings WHERE id IN ({','.join('?' * len(ids))}) "
                            "AND description IS NOT NULL", ids) if ids else []:
        text = web.unspell(row["description"] or "")
        hosts = re.findall(r"(?:https?://|www\.)([a-z0-9.-]+\.[a-z]{2,})", text, re.IGNORECASE)
        hosts += [e.split("@")[1] for e, _ in web.find_emails(text)]
        for h in hosts:
            h = h.lower()
            if not is_job_host(h) and not any(m in h for m in MAIL_PROVIDERS):
                out.append((web.registrable(h), "job text"))
    return out

# The company's own website linked from an ATS job page
def _from_ats_page(url: str, tokens: list[str], slugs: list[str]) -> list[tuple[str, str]]:
    page = web.fetch(url)
    if not page:
        return []
    links = web.read_html(page["html"], page["url"])["links"]
    links += re.findall(r"https?://[a-z0-9.-]+\.[a-z]{2,}", page["html"], re.IGNORECASE)   # e.g. in JSON data
    out = []
    for link in links:
        host = urlparse(link).netloc.lower()
        if not host or is_job_host(host):
            continue
        dom = web.registrable(host)
        label = _plain(dom.split(".")[0]).replace(" ", "")
        if any(t in label for t in tokens if len(t) >= 3) or any(s.replace("-", "") in label for s in slugs):
            out.append((dom, "job page"))
    return out

# Likely domains from the name, kept only if they exist in DNS
def _guesses(company: str, country: str | None, slugs: list[str]) -> list[tuple[str, str]]:
    tokens = name_tokens(company)
    labels = [s.replace("_", "-") for s in slugs]
    if tokens:
        labels += ["".join(tokens), "-".join(tokens)]
        if len(tokens) >= 2 and len(tokens[0]) >= 5:
            labels.append(tokens[0])
    endings = COUNTRY_ENDINGS.get((country or "").upper(), COUNTRY_ENDINGS[""])
    out = []
    for label in dict.fromkeys(l for l in labels if l and len(l) >= 3):
        for end in endings:
            dom = f"{label}.{end}"
            if web.dns(dom, "A") or web.dns(f"www.{dom}", "A"):
                out.append((dom, "guess"))
        if len(out) >= 4:
            break
    return out
#--------------------------------------------------------------#

# The lead's domain: (domain or None, status, source). paid_finder: contacts.find_domain-like callable or None.
def resolve(conn, client_id: int, lead, paid_finder=None) -> tuple[str | None, str, str | None]:
    company = lead["company_name"] or ""
    if lead["domain"] and lead["domain_status"] in ("manual", "confirmed"):
        return lead["domain"], lead["domain_status"], lead["domain_source"]
    tokens = name_tokens(company)
    from_links, slugs, ats_pages = _from_links(lead["links"])
    candidates = ([(lead["domain"], "earlier lookup")] if lead["domain"] else []) + from_links + \
        _from_descriptions(conn, client_id, lead["name_normalized"])
    for url in ats_pages[:2]:
        candidates += _from_ats_page(url, tokens, slugs)

    uncertain, tried = None, set()
    def _try(cands):
        nonlocal uncertain
        for dom, source in cands:
            if not dom or dom in tried or "." not in dom:
                continue
            tried.add(dom)
            status, _ = check_domain(dom, company)
            if status == "confirmed":
                return dom, "confirmed", source
            if source in ("earlier lookup", "job link", "search"):   # worth showing for a manual check
                uncertain = uncertain or (dom, "uncertain", source)
        return None

    found = _try(candidates) or _try(_guesses(company, lead["country"], slugs))
    if found:
        return found
    if paid_finder:
        dom = paid_finder(company, lead["country"])
        if dom:
            found = _try([(dom, "search")])
            if found:
                return found
    return uncertain or (None, "not_found", None)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
