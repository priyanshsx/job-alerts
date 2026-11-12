#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/sources/web_search.py
# Purpose: general web search through Unoblox (not limited to LinkedIn), used to find
#          company websites. Same request format and retries as xray_search.py.
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
SEARCH_URL = "https://api.unoblox.ai/v1/search"
#--------------------------------------------------------------#

# Run one web search and return url, title and snippet for each result
def search(query: str, num: int = 10, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        resp = httpx.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {os.environ['UNOBLOX_SEARCH_API_KEY']}"},
            json={"query": query, "numResults": num},
            timeout=60,
        )
        if resp.status_code == 429:
            time.sleep(float(resp.headers.get("retry-after", "1")))
            continue
        if resp.status_code in (502, 503):
            time.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            body = resp.json()
            raise RuntimeError(f"{body.get('error_code')}: {body.get('error')}")
        break
    else:
        raise RuntimeError("search unavailable after retries")

    returned = len(resp.json().get("results", []))       # Unoblox bills per result returned
    usage.log_call("unoblox_search", returned, returned * usage.unoblox_price())
    return [{"url": item.get("url") or "",
             "title": item.get("title") or "",
             "snippet": item.get("snippet") or " ".join(item.get("highlights") or [])}
            for item in resp.json().get("results", [])]
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
