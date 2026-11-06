#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/emails/apollo.py
# Purpose: Apollo email lookup by LinkedIn profile (People Match).
#          Check Apollo's API docs on the first test run: free plans may limit API access,
#          in which case this provider is skipped automatically.
#--------------------------------------------------------------#

# Imports libraries
import os
import httpx
from job_alerts.emails.base import EmailResult, ProviderUnavailable, split_name
#--------------------------------------------------------------#

# Global variables
NAME = "apollo"
URL = "https://api.apollo.io/api/v1/people/match"
VERIFIED = {"verified"}
#--------------------------------------------------------------#

def find(person: dict, domain: str | None) -> EmailResult:
    key = os.getenv("APOLLO_API_KEY")
    if not key:
        raise ProviderUnavailable("APOLLO_API_KEY not set")
    first, last = split_name(person.get("full_name"))
    payload = {"linkedin_url": person.get("linkedin_url"), "first_name": first, "last_name": last,
               "organization_name": person.get("company_name"), "reveal_personal_emails": False}
    if domain:
        payload["domain"] = domain
    resp = httpx.post(URL, json=payload, timeout=30,
                      headers={"X-Api-Key": key, "Content-Type": "application/json"})
    if resp.status_code in (401, 403):
        raise ProviderUnavailable(f"Apollo refused the request ({resp.status_code}): {resp.text[:150]}")
    if resp.status_code >= 400:
        return EmailResult(None, "error", 0, f"HTTP {resp.status_code}: {resp.text[:150]}")
    found = (resp.json().get("person") or {})
    email, status = found.get("email"), (found.get("email_status") or "").lower()
    if not email or "email_not_unlocked" in email:
        return EmailResult(None, "not_found", 0, status or "no email")
    return EmailResult(email, "verified" if status in VERIFIED else "risky", 1, status)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
