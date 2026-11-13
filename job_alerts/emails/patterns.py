#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/emails/patterns.py
# Purpose: our own email finder. Learns each company's email format from verified emails we find
#          (e.g. "first.last"), guesses addresses for new people, and checks the best guesses with
#          MillionVerifier. Two waterfall steps for contacts.py:
#            pattern  domain's format already known -> 1 check (cheapest, tried first)
#            guess    format unknown -> up to max_guesses checks of the most common formats
#          A domain with no mail server is skipped; a catch-all domain gets one "risky" guess.
#--------------------------------------------------------------#

# Imports libraries
import os
import re
import unicodedata
from datetime import datetime, timezone
import httpx
from job_alerts.core.db import get_conn
from job_alerts.emails import millionverifier
from job_alerts.emails.base import EmailResult, split_name
#--------------------------------------------------------------#

# Global variables: most common formats first
FORMATS = ["first.last", "flast", "first", "firstlast", "f.last", "first_last", "last.first", "firstl",
           "last", "lastf", "first-last"]
MX_PROVIDERS = {"google": ("google.com", "googlemail.com"), "microsoft": ("outlook.com", "microsoft.com"),
                "proofpoint": ("pphosted.com", "ppe-hosted.com"), "mimecast": ("mimecast.com",)}
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
#--------------------------------------------------------------#

# "Müller" -> ["mueller", "muller"]; "Anna-Lena" -> ["annalena", "anna-lena"] ... lower case, a-z only
def _variants(part: str) -> list[str]:
    p = part.lower().strip()
    german = p.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    plain = unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode()
    out = []
    for v in (german, plain):
        for w in (re.sub(r"[^a-z]", "", v), re.sub(r"[^a-z-]", "", v)):
            if w and w not in out:
                out.append(w)
    return out

def _build(fmt: str, first: str, last: str) -> str:
    f, l = first, last
    return {"first.last": f"{f}.{l}", "flast": f"{f[:1]}{l}", "first": f, "firstlast": f"{f}{l}",
            "f.last": f"{f[:1]}.{l}", "first_last": f"{f}_{l}", "last.first": f"{l}.{f}",
            "firstl": f"{f}{l[:1]}", "last": l, "lastf": f"{l}{f[:1]}", "first-last": f"{f}-{l}"}[fmt]

def candidates(full_name: str, domain: str, formats: list[str] | None = None) -> list[str]:
    first, last = split_name(full_name)
    if not first or not last or not domain:
        return []
    out = []
    for fmt in formats or FORMATS:
        for fv in _variants(first)[:2]:
            for lv in _variants(last)[:2]:
                email = f"{_build(fmt, fv, lv)}@{domain}"
                if email not in out:
                    out.append(email)
    return out
#--------------------------------------------------------------#

# Which format a verified email uses for this person (None if it doesn't match one)
def detect_format(full_name: str, email: str) -> str | None:
    local = email.split("@")[0].lower()
    first, last = split_name(full_name)
    for fmt in FORMATS:
        for fv in _variants(first):
            for lv in _variants(last):
                if fv and lv and _build(fmt, fv, lv) == local:
                    return fmt
    return None
#--------------------------------------------------------------#

def _domain_row(domain: str):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM email_domains WHERE domain = ?", (domain,)).fetchone()
    finally:
        conn.close()

def _save_domain(domain: str, **fields) -> None:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO email_domains (domain, checked_at) VALUES (?, ?) "
                     "ON CONFLICT (domain) DO NOTHING", (domain, _now()))
        for k, v in fields.items():
            conn.execute(f"UPDATE email_domains SET {k} = ?, checked_at = ? WHERE domain = ?", (v, _now(), domain))
        conn.commit()
    finally:
        conn.close()
#--------------------------------------------------------------#

# Mail servers of a domain (free, via public DNS over HTTPS) -> provider name, or "none"
def mx_provider(domain: str) -> str:
    row = _domain_row(domain)
    if row and row["mx_provider"]:
        return row["mx_provider"]
    try:
        resp = httpx.get("https://dns.google/resolve", params={"name": domain, "type": "MX"}, timeout=15)
        hosts = [a.get("data", "").lower() for a in resp.json().get("Answer", []) if a.get("type") == 15]
    except Exception:
        return "other"                                  # can't tell: don't block the lookup
    if not hosts:
        provider = "none"
    else:
        provider = next((name for name, marks in MX_PROVIDERS.items()
                         if any(m in h for h in hosts for m in marks)), "other")
    _save_domain(domain, mx_provider=provider)
    return provider
#--------------------------------------------------------------#

# Learn a domain's format from a verified email (called by contacts.py after every verified find)
def learn(full_name: str, email: str) -> None:
    if not email or "@" not in email:
        return
    fmt = detect_format(full_name, email)
    if fmt:
        _save_domain(email.split("@")[1].lower(), pattern=fmt, pattern_source=email)
#--------------------------------------------------------------#

# Check candidates in order; stop at the first verified one
def _check(emails: list[str]) -> EmailResult:
    used = 0
    for email in emails:
        status, detail = millionverifier.verify(email)
        used += 1
        if status == "verified":
            return EmailResult(email, "verified", used, f"guess verified ({detail})")
        if status == "catch_all":
            _save_domain(email.split("@")[1], catch_all=1)
            return EmailResult(emails[0], "risky", used, "catch-all domain: best guess, not verifiable")
    return EmailResult(None, "not_found", used, f"{used} guesses, none verified")
#--------------------------------------------------------------#

# Waterfall step "pattern": only when the domain's format is known
class _Pattern:
    NAME = "pattern"

    @staticmethod
    def find(person: dict, domain: str | None) -> EmailResult:
        if not domain:
            return EmailResult(None, "not_found", 0, "no domain")
        row = _domain_row(domain)
        if not row or not row["pattern"]:
            return EmailResult(None, "not_found", 0, "format not learned yet")
        guesses = candidates(person.get("full_name"), domain, [row["pattern"]])[:2]
        if not guesses:
            return EmailResult(None, "not_found", 0, "needs a first and last name")
        if row["catch_all"]:
            return EmailResult(guesses[0], "risky", 0, f"known format {row['pattern']}, catch-all domain")
        return _check(guesses)
#--------------------------------------------------------------#

# Waterfall step "guess": the most common formats, checked one by one
class _Guess:
    NAME = "guess"

    @staticmethod
    def find(person: dict, domain: str | None) -> EmailResult:
        if not domain:
            return EmailResult(None, "not_found", 0, "no domain")
        if mx_provider(domain) == "none":
            return EmailResult(None, "not_found", 0, f"{domain} has no mail server")
        row = _domain_row(domain)
        limit = int(os.getenv("EMAIL_MAX_GUESSES") or 3)
        guesses = candidates(person.get("full_name"), domain)
        if not guesses:
            return EmailResult(None, "not_found", 0, "needs a first and last name")
        if row and row["catch_all"]:
            return EmailResult(guesses[0], "risky", 0, "catch-all domain: best guess, not verifiable")
        return _check(guesses[:limit])
#--------------------------------------------------------------#

pattern = _Pattern()
guess = _Guess()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
