#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/sources/remote_boards.py
# Purpose: free remote job boards: Remotive (public API, marketing category) and We Work Remotely
#          (public RSS, sales and marketing). Both ask for a link back to the original posting,
#          which every lead keeps in its URL. collect.py applies the client's title filters.
#--------------------------------------------------------------#

# Imports libraries
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import httpx
#--------------------------------------------------------------#

# Global variables
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
WWR_URL = "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss"
HEADERS = {"User-Agent": "job-alerts/1.0 (internal lead research)"}
#--------------------------------------------------------------#

def _plain(text: str | None, limit: int = 4000) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return " ".join(text.split())[:limit]
#--------------------------------------------------------------#

def fetch_remotive(days: int) -> list[dict]:
    resp = httpx.get(REMOTIVE_URL, params={"category": "marketing"}, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for j in resp.json().get("jobs", []):
        posted = j.get("publication_date") or ""
        try:
            if datetime.fromisoformat(posted.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) < since:
                continue
        except ValueError:
            pass
        out.append({"source": "remotive", "external_id": str(j.get("id")), "url": j.get("url"),
                    "title": j.get("title"), "company_name": j.get("company_name"),
                    "location": j.get("candidate_required_location"), "country": "REMOTE",
                    "posted_at": posted[:10], "description": _plain(j.get("description"))})
    return out
#--------------------------------------------------------------#

def fetch_wwr(days: int) -> list[dict]:
    resp = httpx.get(WWR_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for item in ET.fromstring(resp.content).iter("item"):
        raw_title = item.findtext("title") or ""             # "Acme: Head of Content"
        company, _, title = raw_title.partition(": ")
        link = item.findtext("link") or ""
        try:
            posted = parsedate_to_datetime(item.findtext("pubDate") or "")
            if posted < since:
                continue
            posted_text = posted.date().isoformat()
        except (TypeError, ValueError):
            posted_text = None
        out.append({"source": "weworkremotely", "external_id": link.rstrip("/").split("/")[-1],
                    "url": link, "title": title or raw_title, "company_name": company if title else None,
                    "location": item.findtext("region"), "country": "REMOTE", "posted_at": posted_text,
                    "description": _plain(item.findtext("description"))})
    return out
#--------------------------------------------------------------#

def fetch(days: int = 7) -> list[dict]:
    postings = []
    for name, fn in (("Remotive", fetch_remotive), ("We Work Remotely", fetch_wwr)):
        try:
            postings += fn(days)
        except Exception as e:                       # one board down must not stop the other
            print(f"  {name} failed: {e}")
    return postings
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
