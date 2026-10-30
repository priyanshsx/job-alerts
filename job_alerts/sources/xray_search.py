#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import os 
import time 
from urllib.parse import urlparse 
import httpx 
from dotenv import load_dotenv
from job_alerts.core.db import ROOT 
#--------------------------------------------------------------#

# Global variables 
load_dotenv(ROOT / ".env")
SEARCH_URL = "https://api.unoblox.ai/v1/search"
#--------------------------------------------------------------#

# Standardizes the LinkedIn url for parsing 
def normalize_linkedin_url(url: str) -> str:
    parts = urlparse(url.strip()).path.strip("/").split("/")
    if "in" in parts and parts.index("in") + 1 < len(parts):
        handle = parts[parts.index("in") + 1].lower()
        return f"https://www.linkedin.com/in/{handle}"
    return url.strip()
#--------------------------------------------------------------#

# Searches the web for linkedin and returns only profile results 
def search(query: str, num: int = 20, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        resp = httpx.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {os.environ['UNOBLOX_API_KEY']}"},
            json={"query": query, "numResults": num, "includeDomains": ["linkedin.com"]},
            timeout=60
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
    results = []
    for item in resp.json().get("results", []):
        url = item.get("url") or ""
        if "linked.com/in/" not in url:
            continue
        results.append({
            "url": normalize_linkedin_url(url),
            "title": item.get("title") or "",
            "snippet": item.get("snippet") or " ".join(item.get("highlights") or [])
        })
    return results 
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#