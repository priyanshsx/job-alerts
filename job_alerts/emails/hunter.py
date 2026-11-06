#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/emails/hunter.py
# Purpose: Hunter email lookup by name + company domain (Email Finder).
#--------------------------------------------------------------#

# Imports libraries
import os
import httpx
from job_alerts.emails.base import EmailResult, ProviderUnavailable, split_name
#--------------------------------------------------------------#

# Global variables
NAME = "hunter"
URL = "https://api.hunter.io/v2/email-finder"
#--------------------------------------------------------------#

def find(person: dict, domain: str | None) -> EmailResult:
    key = os.getenv("HUNTER_API_KEY")
    if not key:
        raise ProviderUnavailable("HUNTER_API_KEY not set")
    first, last = split_name(person.get("full_name"))
    if not domain or not first or not last:
        return EmailResult(None, "not_found", 0, "needs a domain and a first and last name")
    resp = httpx.get(URL, params={"domain": domain, "first_name": first, "last_name": last,
                                  "api_key": key}, timeout=30)
    if resp.status_code in (401, 403):
        raise ProviderUnavailable(f"Hunter refused the request ({resp.status_code}): {resp.text[:150]}")
    if resp.status_code == 404:
        return EmailResult(None, "not_found", 0, "no match")
    if resp.status_code >= 400:
        return EmailResult(None, "error", 0, f"HTTP {resp.status_code}: {resp.text[:150]}")
    data = resp.json().get("data") or {}
    email = data.get("email")
    if not email:
        return EmailResult(None, "not_found", 0, "no email")
    status = ((data.get("verification") or {}).get("status") or "").lower()
    return EmailResult(email, "verified" if status == "valid" else "risky", 1, status or f"score {data.get('score')}")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
