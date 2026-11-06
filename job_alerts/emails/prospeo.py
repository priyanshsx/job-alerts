#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/emails/prospeo.py
# Purpose: Prospeo email lookup by LinkedIn profile.
#          Prospeo has changed its endpoints before: check the URL and fields against its API
#          docs on the first test run, and adjust URL / the two marked lines if needed.
#--------------------------------------------------------------#

# Imports libraries
import os
import httpx
from job_alerts.emails.base import EmailResult, ProviderUnavailable
#--------------------------------------------------------------#

# Global variables
NAME = "prospeo"
URL = "https://api.prospeo.io/enrich-person"
#--------------------------------------------------------------#

def find(person: dict, domain: str | None) -> EmailResult:
    key = os.getenv("PROSPEO_API_KEY")
    if not key:
        raise ProviderUnavailable("PROSPEO_API_KEY not set")
    resp = httpx.post(URL, json={"data": {"linkedin_url": person.get("linkedin_url")}},   # ← check
                      headers={"X-KEY": key, "Content-Type": "application/json"}, timeout=30)
    if resp.status_code in (401, 403):
        raise ProviderUnavailable(f"Prospeo refused the request ({resp.status_code}): {resp.text[:150]}")
    body = resp.json() if resp.content else {}
    if resp.status_code >= 400 or body.get("error"):
        code = body.get("error_code") or f"HTTP {resp.status_code}"
        if "NO_MATCH" in str(code).upper() or resp.status_code == 404:
            return EmailResult(None, "not_found", 0, str(code))
        return EmailResult(None, "error", 0, str(code))
    email_info = ((body.get("person") or {}).get("email") or {})                            # ← check
    email = email_info.get("email") if isinstance(email_info, dict) else email_info
    status = (email_info.get("status") or "").lower() if isinstance(email_info, dict) else ""
    if not email:
        return EmailResult(None, "not_found", 0, status or "no email")
    return EmailResult(email, "verified" if status in ("verified", "valid") else "risky", 1, status)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
