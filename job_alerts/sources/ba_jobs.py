#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import time 
import httpx 
#--------------------------------------------------------------#

# Global Variables 
BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PAGE_SIZE = 50

COUNTRY_CODES = {"DEUTSCHLAND": "DE", "ÖSTERREICH": "AT", "SCHWEIZ": "CH"}
#--------------------------------------------------------------#

# Searches for the required job postings 
def _search(keyword: str, days: int, page: int) -> dict:
    params = {
        "was": keyword, 
        "angebotsart": 1, 
        "veroeffentlichtseit": days, 
        "page": page, 
        "size": PAGE_SIZE
    }
    resp = httpx.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()
#--------------------------------------------------------------#

# Returns normalized postings for the given keywords 
def fetch(keyword: str, days: int = 2, max_pages: int = 5) -> list[dict]:
    postings = []
    for page in range(1, max_pages + 1):
        items = _search(keyword, days, page).get("ergebnisliste", [])
        postings += [_normalize(item) for item in items]
        if len(items) < PAGE_SIZE:
            break 
        time.sleep(1)
    return postings 
#--------------------------------------------------------------#

# Turns the API's German field names into the standard shape
def _normalize(item: dict) -> dict:
    locations = item.get("stellenlokationen") or [{}]
    address = locations[0].get("adresse") or {}
    refnr = item["referenznummer"]

    return {
        "source": "ba_jobs",
        "external_id": refnr, 
        "title": item.get("stellenangebotsTitel"),
        "company_name": item.get("firma"),
        "location": address.get("ort"),
        "country": COUNTRY_CODES.get(address.get("land"), address.get("land")),
        "posted_at": item.get("datumErsteVeroeffentlichung"),
        "url": item.get("externeURL")
            or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
    }
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#