#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/sources/serper.py
# Purpose: Google search through Serper (the same service content-suggester uses), with a
#          recency filter. Used to find job pages on company job boards and LinkedIn jobs.
#--------------------------------------------------------------#

# Imports libraries
import os
import time
import httpx
from dotenv import load_dotenv
from job_alerts.core import usage
from job_alerts.core.db import ROOT
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
SERPER_URL = "https://google.serper.dev/search"
#--------------------------------------------------------------#

# Google's time filter for "the last N days": day, week, month or year
def period_for(days: int) -> str:
    return "d" if days <= 1 else "w" if days <= 7 else "m" if days <= 31 else "y"
#--------------------------------------------------------------#

# One Google search; returns the organic results (title, link, snippet, date)
def search(query: str, days: int = 7, num: int = 20, retries: int = 3) -> list[dict]:
    key = os.getenv("SERPER_API_KEY")
    if not key:
        raise RuntimeError("SERPER_API_KEY is not set in job-alerts' .env "
                           "(copy it from content-suggester's .env)")
    payload = {"q": query, "tbs": f"qdr:{period_for(days)}", "num": num}
    for attempt in range(retries):
        try:
            resp = httpx.post(SERPER_URL, json=payload, timeout=60,
                              headers={"X-API-KEY": key, "Content-Type": "application/json"})
        except httpx.HTTPError as e:                  # timeout or connection problem: wait and retry
            if attempt == retries - 1:
                raise RuntimeError(f"Serper unreachable for {query!r}: {e or type(e).__name__}")
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (429, 502, 503):
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 400 and payload["num"] != 10:
            payload["num"] = 10                      # some plans only accept 10 results per search
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"Serper {resp.status_code} for {query!r}: {resp.text[:300]}")
        credits = 1 if payload["num"] <= 10 else 2      # 1 credit per 10 results
        usage.log_call("serper", credits, credits * usage.serper_price())
        return resp.json().get("organic", [])
    raise RuntimeError("Serper unavailable after retries")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
