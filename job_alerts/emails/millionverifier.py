#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/emails/millionverifier.py
# Purpose: verify one email address with MillionVerifier's real-time API.
#          Returns "verified" (ok), "catch_all" (domain accepts everything), "invalid" (also
#          disposable), "unknown" (the server didn't say), or "error". Every call is logged as a cost.
#          .env: MILLIONVERIFIER_API_KEY, optional MILLIONVERIFIER_USD_PER_CHECK (0: free credits).
#--------------------------------------------------------------#

# Imports libraries
import os
import httpx
from job_alerts.core import usage
from job_alerts.emails.base import ProviderUnavailable
#--------------------------------------------------------------#

# Global variables
URL = os.getenv("MILLIONVERIFIER_URL", "https://api.millionverifier.com/api/v3/")
#--------------------------------------------------------------#

def verify(email: str) -> tuple[str, str]:
    key = os.getenv("MILLIONVERIFIER_API_KEY")
    if not key:
        raise ProviderUnavailable("MILLIONVERIFIER_API_KEY not set")
    try:
        resp = httpx.get(URL, params={"api": key, "email": email, "timeout": 20}, timeout=40)
    except httpx.HTTPError as e:
        return "error", f"unreachable: {e or type(e).__name__}"
    usage.log_call("millionverifier", 1, float(os.getenv("MILLIONVERIFIER_USD_PER_CHECK") or 0))
    if resp.status_code in (401, 403):
        raise ProviderUnavailable(f"MillionVerifier refused the key ({resp.status_code})")
    try:
        body = resp.json()
    except ValueError:
        return "error", f"HTTP {resp.status_code}: {resp.text[:120]}"
    if body.get("error"):
        if "api" in str(body["error"]).lower() and "key" in str(body["error"]).lower():
            raise ProviderUnavailable(f"MillionVerifier: {body['error']}")
        return "error", str(body["error"])[:150]
    result = str(body.get("result") or body.get("status") or "").lower()
    detail = f"{result} / {body.get('subresult', '')} / quality {body.get('quality', '')}".strip()
    if result in ("ok", "valid"):
        return "verified", detail
    if result in ("catch_all", "catchall", "catch-all"):
        return "catch_all", detail
    if result in ("invalid", "disposable"):
        return "invalid", detail
    return "unknown", detail
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
