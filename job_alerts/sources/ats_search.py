#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/sources/ats_search.py
# Purpose: find recent job postings on company job boards (Greenhouse, Lever, Ashby, Workable)
#          and LinkedIn job pages, through Google search results only. Never visits LinkedIn.
#          One search per role per site, with all markets combined into the query.
#--------------------------------------------------------------#

# Imports libraries
import re
from urllib.parse import urlparse
from job_alerts.sources import serper
#--------------------------------------------------------------#

# Global variables: site -> (Google "site:" filter, pattern for a single job page)
SITES = {
    "greenhouse": ("(site:boards.greenhouse.io OR site:job-boards.greenhouse.io)",
                   re.compile(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)")),
    "lever": ("site:jobs.lever.co", re.compile(r"jobs\.lever\.co/([^/?#]+)/([0-9a-f-]{20,})")),
    "ashby": ("site:jobs.ashbyhq.com", re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{20,})")),
    "workable": ("site:apply.workable.com", re.compile(r"apply\.workable\.com/([^/?#]+)/j/([0-9A-F]+)", re.I)),
    "linkedin_jobs": ("site:linkedin.com/jobs/view", re.compile(r"linkedin\.com/jobs/view/([^/?#]*?)-?(\d{6,})")),
}

# Market -> words that show a posting is in that market (for the country column)
MARKET_HINTS = {
    "IN": ["india", "bengaluru", "bangalore", "mumbai", "delhi", "gurugram", "gurgaon", "noida",
           "pune", "hyderabad", "chennai"],
    "GB": ["united kingdom", "london", "manchester", "edinburgh", "england", " uk"],
    "SG": ["singapore"],
    "US": ["united states", "new york", "san francisco", "austin", "boston", "seattle",
           "los angeles", "chicago", " usa", ", ny", ", ca"],
}
#--------------------------------------------------------------#

def _country(text: str) -> str | None:
    t = f" {text.lower()}"
    for code, hints in MARKET_HINTS.items():
        if any(h in t for h in hints):
            return code
    return "REMOTE" if "remote" in t else None
#--------------------------------------------------------------#

# Pull "role" and "company" out of each site's page-title format
def _title_and_company(site: str, title: str, slug: str) -> tuple[str, str]:
    title = re.sub(r"\s*\|\s*LinkedIn\s*$", "", title or "").strip()
    company_from_slug = slug.replace("-", " ").replace("_", " ").title()
    if site == "linkedin_jobs":                      # "Acme hiring Head of Content in Bengaluru, India"
        m = re.match(r"(.+?) hiring (.+?)(?: in (.+))?$", title)
        if m:
            return m.group(2).strip(), m.group(1).strip()
        return title, ""
    if site == "greenhouse":                         # "Job Application for Head of Content at Acme"
        m = re.match(r"(?:Job Application for )?(.+?) at (.+)$", title)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    if site == "lever":                              # "Acme - Head of Content"
        parts = [p.strip() for p in title.split(" - ", 1)]
        if len(parts) == 2:
            return parts[1], parts[0]
    if site == "ashby":                              # "Head of Content @ Acme"
        if " @ " in title:
            role, company = title.rsplit(" @ ", 1)
            return role.strip(), company.strip()
    if site == "workable":                           # "Head of Content - Acme"
        parts = [p.strip() for p in title.rsplit(" - ", 1)]
        if len(parts) == 2:
            return parts[0], parts[1]
    return title, company_from_slug
#--------------------------------------------------------------#

# Search one role on every site; returns postings in the standard shape used by collect.py
def fetch(role: str, markets: list[str], days: int = 7, sites: list[str] | None = None) -> list[dict]:
    market_filter = " OR ".join(f'"{m}"' for m in markets)
    postings = []
    for site in sites or list(SITES):
        site_filter, pattern = SITES[site]
        query = f'{site_filter} "{role}"' + (f" ({market_filter})" if markets else "")
        for r in serper.search(query, days=days):
            url = r.get("link", "")
            m = pattern.search(url)
            if not m:
                continue                             # not a single job page (e.g. a company's job list)
            slug, job_id = m.group(1), m.group(2)
            title, company = _title_and_company(site, r.get("title", ""), slug)
            snippet = r.get("snippet", "")
            postings.append({
                "source": site,
                "external_id": job_id,
                "url": url.split("?")[0],
                "title": title,
                "company_name": company or slug.replace("-", " ").title(),
                "location": None,
                "country": _country(f"{r.get('title', '')} {snippet}"),
                "posted_at": r.get("date"),
                "description": f"{r.get('title', '')}\n{snippet}".strip(),
            })
    return postings
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
