#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/crawler/finder.py
# Purpose: turn website evidence into one checked email for a person, cheapest first:
#            found on site    the person's own address was on a public page
#            company format   built from the format seen on the site (or learned from a verified find)
#            common format    the usual formats, only when nothing is known (up to 3 checks)
#          Every address is checked with MillionVerifier before it reaches the sheet. Answers are
#          cached in email_verifications, so no address is ever paid for twice. On a catch-all
#          domain only evidence-backed addresses are kept ("catch-all"); bare guesses are dropped.
#          Checks are logged in email_lookups as provider "crawler" and use the client's
#          MillionVerifier budget (contacts.email_providers -> pattern -> monthly_limit).
#--------------------------------------------------------------#

# Imports libraries
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from job_alerts.core.names import normalize_name
from job_alerts.emails import millionverifier, patterns
from job_alerts.emails.base import split_name
#--------------------------------------------------------------#

# Global variables
CACHE_DAYS = 90
MAX_COMMON_GUESSES = int(os.getenv("EMAIL_MAX_GUESSES") or 3)
#--------------------------------------------------------------#

class OutOfCredits(Exception):
    pass
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
#--------------------------------------------------------------#

# MillionVerifier answers for this client, with a monthly budget
class Verifier:
    def __init__(self, conn, client_id: int, credits_left: int):
        self.conn, self.client_id, self.left = conn, client_id, credits_left

    def check(self, email: str, person_id: int | None) -> str:
        row = self.conn.execute("SELECT status, checked_at FROM email_verifications WHERE email = ?",
                                (email,)).fetchone()
        fresh = row and row["status"] not in ("error", "unknown") and \
            datetime.fromisoformat(row["checked_at"]) > datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)
        if fresh:
            return row["status"]
        if self.left <= 0:
            raise OutOfCredits()
        status, detail = millionverifier.verify(email)
        self.left -= 1
        self.conn.execute("INSERT INTO email_verifications (email, status, detail, checked_at) VALUES (?, ?, ?, ?) "
                          "ON CONFLICT (email) DO UPDATE SET status = excluded.status, detail = excluded.detail, "
                          "checked_at = excluded.checked_at", (email, status, detail, _now()))
        self.conn.execute("INSERT INTO email_lookups (client_id, person_id, provider, result, email, email_status, "
                          "credits, detail, created_at) VALUES (?, ?, 'crawler', ?, ?, ?, 1, ?, ?)",
                          (self.client_id, person_id, "found" if status in ("verified", "catch_all") else "not_found",
                           email, status, detail, _now()))
        self.conn.commit()
        return status
#--------------------------------------------------------------#

# The mail domain: where the site really lives (after redirects), unless its addresses all use
# another one (e.g. a group domain)
def mail_domain(site_domain: str, emails: list[dict], company: str, home_url: str | None = None) -> str:
    from job_alerts.crawler.web import registrable
    from urllib.parse import urlparse
    if home_url:
        site_domain = registrable(urlparse(home_url).netloc) or site_domain
    personal = Counter(e["email"].split("@")[1] for e in emails if not e["is_generic"])
    if not personal:                                 # only info@ / jobs@: their domain is still a hint
        personal = Counter(e["email"].split("@")[1] for e in emails)
        top = personal.most_common(1)
        return site_domain if not top or personal.get(site_domain) else top[0][0]
    if personal.get(site_domain):
        return site_domain
    tokens = [t for t in normalize_name(company).split() if len(t) >= 3]
    for dom, n in personal.most_common():
        if n >= 2 and any(t in dom for t in tokens):
            return dom
    return site_domain
#--------------------------------------------------------------#

# The domain's format: learned from a verified find, else the most common one seen on the site
def known_format(conn, domain: str, emails: list[dict]) -> tuple[str | None, str | None]:
    row = conn.execute("SELECT pattern, pattern_source FROM email_domains WHERE domain = ?", (domain,)).fetchone()
    if row and row["pattern"]:
        return row["pattern"], f"verified {row['pattern_source']}"
    seen = Counter(e["email_format"] for e in emails
                   if e["email_format"] and e["email"].endswith("@" + domain))
    if not seen:
        return None, None
    fmt = seen.most_common(1)[0][0]
    example = next(e for e in emails if e["email_format"] == fmt and e["email"].endswith("@" + domain))
    return fmt, example["source_url"]
#--------------------------------------------------------------#

# One person's email. Returns {"email", "status", "method", "source"}; email None when unresolved.
# common: how many common formats to try when the site gave no format (0 = none)
def find(conn, verifier: Verifier, name: str, domain: str, emails: list[dict], person_id: int | None,
         common: int = MAX_COMMON_GUESSES, own_email: str | None = None, own_source: str | None = None) -> dict:
    none = {"email": None, "status": "unresolved", "method": None, "source": None}
    first, last = split_name(name)
    if not first or not last:
        return {**none, "status": "unresolved (needs first and last name)"}
    if patterns.mx_provider(domain) == "none":
        return {**none, "status": "no mail server"}

    # Candidates, best evidence first
    cands = []
    if own_email:
        cands.append((own_email, "found on site", own_source))
    for e in emails:
        if e["email"].endswith("@" + domain) and not e["is_generic"] and patterns.detect_format(name, e["email"]) \
                and patterns.detect_format(name, e["email"]) not in ("first", "last"):
            cands.append((e["email"], "found on site", e["source_url"]))
    fmt, fmt_source = known_format(conn, domain, emails)
    if fmt:
        cands += [(c, "company format", fmt_source) for c in patterns.candidates(name, domain, [fmt])[:2]]
    elif common:
        cands += [(c, "common format", None) for c in
                  patterns.candidates(name, domain, ["first.last", "f.last", "flast", "first"])[:common]]
    seen, unique = set(), []
    for c in cands:
        if c[0] not in seen:
            seen.add(c[0])
            unique.append(c)
    if not unique:
        return none

    # Known catch-all domain: nothing to verify; keep only evidence-backed addresses
    row = conn.execute("SELECT catch_all FROM email_domains WHERE domain = ?", (domain,)).fetchone()
    if row and row["catch_all"]:
        email, method, source = unique[0]
        if method == "common format":
            return {**none, "status": "unresolved (catch-all, format unknown)"}
        return {"email": email, "status": "catch-all", "method": method, "source": source}

    for email, method, source in unique:
        status = verifier.check(email, person_id)
        if status == "verified":
            patterns.learn(name, email)              # remember the format for everyone at this company
            return {"email": email, "status": "verified", "method": method, "source": source}
        if status == "catch_all":
            patterns._save_domain(domain, catch_all=1)
            if method == "common format":
                return {**none, "status": "unresolved (catch-all, format unknown)"}
            return {"email": email, "status": "catch-all", "method": method, "source": source}
    return none
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
