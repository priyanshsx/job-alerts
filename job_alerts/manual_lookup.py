#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/manual_lookup.py
# Purpose: the "Manual Lookup" tab. Paste LinkedIn profile links in column A (one per row);
#          the contacts command (or "lookup") then, for each link:
#            1. reads the person's name, title and company from a search result for that profile
#               (we never open LinkedIn itself)
#            2. finds the company's domain and the email (same waterfall and budgets as contacts)
#            3. adds the person to the People tab at row 2; someone already there is moved to row 2
#          The link is then cleared, so the tab is empty again. A line that isn't a LinkedIn
#          profile link stays, with a note next to it.
#--------------------------------------------------------------#

# Imports libraries
import re
from datetime import datetime, timezone
from pydantic import BaseModel
from job_alerts.core.llm import call_llm
from job_alerts.core.sheets import open_worksheet
from job_alerts.sources import xray_search
from job_alerts.sources.xray_search import normalize_linkedin_url
#--------------------------------------------------------------#

# Global variables
DEFAULT_TAB = "Manual Lookup"
HEADER = ["Paste LinkedIn profile links below (one per row), then run: "
          "python3 -m job_alerts lookup --client <client>", "Note"]
PROFILE_LINK = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[^\s/?#,;]+", re.IGNORECASE)
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
#--------------------------------------------------------------#

# LLM answer shape: what one profile search result says about the person
class Profile(BaseModel):
    full_name: str | None
    title: str | None
    company_name: str | None
    location: str | None
#--------------------------------------------------------------#

PROFILE_PROMPT = """This is a search result for one LinkedIn profile.
Extract the person's full name, CURRENT job title, CURRENT company and location.
Use only what the text says; anything not stated is null. Never guess a company.

Result title: {title}
Result text: {snippet}"""
#--------------------------------------------------------------#

# Open the tab (created if missing) and make sure the header is there
def open_tab(cfg):
    sheets_cfg = getattr(cfg, "sheets", None) or {}
    if not sheets_cfg.get("spreadsheet_id"):
        return None
    ws = open_worksheet(sheets_cfg["spreadsheet_id"], sheets_cfg.get("lookup_tab", DEFAULT_TAB))
    values = ws.get_all_values()
    if not values or not values[0] or values[0][0] != HEADER[0]:
        ws.update(range_name="A1", values=[HEADER])
    return ws
#--------------------------------------------------------------#

# Read the pasted links: returns [(row number, link)] in pasted order, and the rows that had no link
def read_links(ws) -> tuple[list[tuple[int, str]], list[int]]:
    links, bad_rows, seen = [], [], set()
    for row_number, row in enumerate(ws.col_values(1)[1:], start=2):
        text = (row or "").strip()
        if not text:
            continue
        found = PROFILE_LINK.findall(text)
        if not found:
            bad_rows.append(row_number)
            continue
        for link in found:
            url = normalize_linkedin_url(link if link.lower().startswith("http") else "https://" + link)
            if url not in seen:
                seen.add(url)
                links.append((row_number, url))
    return links, bad_rows
#--------------------------------------------------------------#

# Name, title and company for one profile, from a search result for that exact profile
def resolve_profile(client_id: int, url: str) -> dict:
    handle = url.rsplit("/", 1)[-1]
    words = re.sub(r"[-_]+", " ", re.sub(r"-?[0-9a-f]{6,}$", "", handle)).strip()
    try:
        results = xray_search.search(f"{words} linkedin.com/in/{handle}", num=5)
    except (RuntimeError, KeyError) as e:
        print(f"    profile search failed: {e}")
        results = []
    match = next((r for r in results if r["url"] == url), None)
    if not match:
        return {}
    profile = call_llm("manual_lookup_profile",
                       PROFILE_PROMPT.format(title=match["title"], snippet=match["snippet"][:1500]),
                       Profile, client_id, max_tokens=300)
    return profile.model_dump()
#--------------------------------------------------------------#

# Add a new person, or fill in the gaps of one we already have; returns the person's row
def save_person(conn, client_id: int, url: str, profile: dict):
    conn.execute(
        """INSERT INTO people (client_id, full_name, title, company_name, location, linkedin_url, source,
           reason, priority, status, find_email, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'manual_lookup', 'Added by hand (Manual Lookup tab)', 1, 'sent', 1, ?)
           ON CONFLICT (client_id, linkedin_url) DO UPDATE SET
             full_name = COALESCE(people.full_name, excluded.full_name),
             title = COALESCE(people.title, excluded.title),
             company_name = COALESCE(people.company_name, excluded.company_name),
             location = COALESCE(people.location, excluded.location),
             find_email = 1""",
        (client_id, profile.get("full_name"), profile.get("title"), profile.get("company_name"),
         profile.get("location"), url, _now()))
    conn.commit()
    return conn.execute("SELECT * FROM people WHERE client_id = ? AND linkedin_url = ?",
                        (client_id, url)).fetchone()
#--------------------------------------------------------------#

# Clear the handled links; put a note next to lines that weren't profile links
def tidy_tab(ws, done_rows: set[int], bad_rows: list[int]) -> None:
    updates = [{"range": f"A{r}:B{r}", "values": [["", ""]]} for r in sorted(done_rows)]
    updates += [{"range": f"B{r}", "values": [["not a LinkedIn profile link (needs linkedin.com/in/...)"]]}
                for r in bad_rows]
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
#--------------------------------------------------------------#

# The lookup itself. find_domain and find_email come from contacts.py (passed in to avoid a loop).
# Returns the person ids in pasted order, for people_sync to put at the top of the People tab.
def run_lookups(conn, cfg, client_id: int, find_domain, find_email, providers: list[dict],
                unavailable: set[str], waiting: str) -> list[int]:
    ws = open_tab(cfg)
    if ws is None:
        return []
    links, bad_rows = read_links(ws)
    if not links:
        tidy_tab(ws, set(), bad_rows)
        return []

    person_ids, done_rows = [], set()
    for row_number, url in links:
        print(f"  manual lookup: {url}")
        existing = conn.execute("SELECT * FROM people WHERE client_id = ? AND linkedin_url = ?",
                                (client_id, url)).fetchone()
        has_details = existing and existing["full_name"] and existing["company_name"]
        profile = {} if has_details else resolve_profile(client_id, url)
        person = save_person(conn, client_id, url, profile)

        if person["email"] and person["email_status"] == "verified":
            print(f"    already known: {person['email']}")      # no credits spent twice
        else:
            domain = find_domain(conn, cfg, client_id, person["company_name"], None) \
                if person["company_name"] else None
            email, status, source = find_email(conn, client_id, dict(person), domain, providers, unavailable)
            if not email and person["email"]:                 # keep an earlier (risky) email over nothing
                email, status, source = person["email"], person["email_status"], person["email_source"]
            conn.execute("UPDATE people SET email = ?, email_status = ?, email_source = ?, "
                         "email_checked_at = ? WHERE id = ?",
                         (email, status, source, None if status == waiting else _now(), person["id"]))
            conn.commit()
            print(f"    {person['full_name'] or 'name not found'} ({person['company_name'] or 'company not found'})"
                  f", email: {email or status}")
        person_ids.append(person["id"])
        done_rows.add(row_number)

    tidy_tab(ws, done_rows, bad_rows)
    return person_ids
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
