#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/manual_lookup.py
# Purpose: the "Manual Lookup" tab. One row per person or company:
#            column A  LinkedIn profile link (optional)
#            column B  company website or domain, e.g. "firma.de"
#            column C  person's name (optional), e.g. "Michael Weber"
#            column D  person's title (optional), e.g. "Head of IT"
#            column E  Note (written by the engine)
#          The enrich crawler (every 10 minutes) and the "lookup" command read the tab. Per row:
#            name + domain   -> no search and no LLM: only MillionVerifier checks (cheapest)
#            domain only     -> the crawler looks for a person on the website (Impressum, team page)
#            link only       -> name, title and company from a search result for that exact profile
#                               (one Unoblox search + one LLM call; we never open LinkedIn itself)
#          The row becomes (or updates) a lead in the Leads tab: an existing lead with the same
#          domain or company is reused, the typed domain always wins, and the person becomes its
#          contact. The row is then cleared and the crawler finds and verifies the email.
#--------------------------------------------------------------#

# Imports libraries
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from pydantic import BaseModel
from job_alerts.core.llm import call_llm
from job_alerts.core.names import normalize_name
from job_alerts.core.sheets import open_worksheet
from job_alerts.sources import xray_search
from job_alerts.sources.xray_search import normalize_linkedin_url
#--------------------------------------------------------------#

# Global variables
DEFAULT_TAB = "Manual Lookup"
HEADER = ["LinkedIn profile link (optional)", "Company domain, e.g. firma.de",
          "Person's name (optional)", "Person's title (optional)", "Note"]
NOTE_COL = "E"
PROFILE_LINK = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[^\s/?#,;]+", re.IGNORECASE)
DOMAIN = re.compile(r"^(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24})(?:[/?#].*)?$", re.IGNORECASE)
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

# Open the tab (created if missing) and make sure the header is there. An older layout's notes
# (in column B or C) are cleared so they aren't read as domains or names.
def open_tab(cfg):
    sheets_cfg = getattr(cfg, "sheets", None) or {}
    if not sheets_cfg.get("spreadsheet_id"):
        return None
    ws = open_worksheet(sheets_cfg["spreadsheet_id"], sheets_cfg.get("lookup_tab", DEFAULT_TAB))
    values = ws.get_all_values()
    header = values[0] if values else []
    if header[:len(HEADER)] != HEADER:
        if "Note" in header and header.index("Note") < len(HEADER) - 1 and len(values) > 1:
            col = chr(ord("A") + header.index("Note"))
            ws.update(range_name=f"{col}2:{col}{len(values)}", values=[[""] for _ in values[1:]])
        ws.update(range_name="A1", values=[HEADER])
    return ws
#--------------------------------------------------------------#

# "https://www.firma.de/kontakt" -> "firma.de"; None if it isn't a domain
def clean_domain(text: str) -> str | None:
    m = DOMAIN.match((text or "").strip())
    if not m or "linkedin." in m.group(1).lower():
        return None
    from job_alerts.crawler.web import registrable
    return registrable(urlparse("https://" + m.group(1).lower()).netloc)
#--------------------------------------------------------------#

# Read the rows: [{"row", "link", "domain", "name", "title"}] and {row: note} for rows that can't be used
def read_rows(ws) -> tuple[list[dict], dict[int, str]]:
    rows, bad, seen = [], {}, set()
    for row_number, row in enumerate(ws.get_all_values()[1:], start=2):
        cells = [(c or "").strip() for c in row] + [""] * 4
        a, b, name, title = cells[0], cells[1], cells[2], cells[3]
        if not (a or b or name):
            continue
        links = []
        for link in PROFILE_LINK.findall(a):
            url = normalize_linkedin_url(link if link.lower().startswith("http") else "https://" + link)
            if url not in seen:
                seen.add(url)
                links.append(url)
        domain = clean_domain(b) or (clean_domain(a) if not links else None)
        if b and not domain:
            bad[row_number] = "column B isn't a domain (e.g. firma.de)"
            continue
        if not links and not domain:
            bad[row_number] = "needs a domain in column B (or a LinkedIn profile link in column A)"
            continue
        for url in links or [None]:
            rows.append({"row": row_number, "link": url, "domain": domain,
                         "name": name or None, "title": title or None})
    return rows, bad
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

# Add a new person (only rows with a LinkedIn link), or fill the gaps of one we have; returns the row
def save_person(conn, client_id: int, url: str, profile: dict):
    conn.execute(
        """INSERT INTO people (client_id, full_name, title, company_name, location, linkedin_url, source,
           reason, priority, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'manual_lookup', 'Added by hand (Manual Lookup tab)', 1, 'sent', ?)
           ON CONFLICT (client_id, linkedin_url) DO UPDATE SET
             full_name = COALESCE(excluded.full_name, people.full_name),
             title = COALESCE(excluded.title, people.title),
             company_name = COALESCE(people.company_name, excluded.company_name),
             location = COALESCE(people.location, excluded.location)""",
        (client_id, profile.get("full_name"), profile.get("title"), profile.get("company_name"),
         profile.get("location"), url, _now()))
    conn.commit()
    return conn.execute("SELECT * FROM people WHERE client_id = ? AND linkedin_url = ?",
                        (client_id, url)).fetchone()
#--------------------------------------------------------------#

# Create or update the lead for one row; returns the lead id.
# contact: {"name", "title", "linkedin", "person_id", "email", "email_status"} or None
def save_lead(conn, client_id: int, company: str, domain: str | None, contact: dict | None) -> int:
    lead = None
    if domain:                                       # an existing lead with this domain is reused
        lead = conn.execute("SELECT * FROM leads WHERE client_id = ? AND domain = ? ORDER BY id LIMIT 1",
                            (client_id, domain)).fetchone()
    if lead is None:
        key = normalize_name(company) or company.lower()
        now = _now()
        conn.execute(
            """INSERT INTO leads (client_id, company_name, name_normalized, sources, latest_signal,
               latest_signal_at, priority, status, created_at, updated_at)
               VALUES (?, ?, ?, 'manual_lookup', 'Added by hand (Manual Lookup tab)', ?, 1, 'new', ?, ?)
               ON CONFLICT (client_id, name_normalized) DO UPDATE SET updated_at = excluded.updated_at""",
            (client_id, company, key, now, now, now))
        lead = conn.execute("SELECT * FROM leads WHERE client_id = ? AND name_normalized = ?",
                            (client_id, key)).fetchone()
    sources = [s.strip() for s in (lead["sources"] or "").split(",") if s.strip()]
    fields = {"sources": ", ".join(dict.fromkeys(sources + ["manual_lookup"])), "enrich_next_at": None,
              "enrich_attempts": 0}
    if domain:
        fields.update(domain=domain, domain_status="manual", domain_source="manual")
    same = contact and (lead["contact_name"] or "").strip().lower() == (contact["name"] or "").strip().lower()
    if contact and contact["name"] and not same:
        if lead["contact_email"] and lead["contact_source"] == "website":   # keep the website person as 2nd
            fields.update(extra_name=lead["contact_name"], extra_title=lead["contact_title"],
                          extra_email=lead["contact_email"], extra_email_status=lead["email_status"])
        verified = contact.get("email") and contact.get("email_status") == "verified"
        fields.update(contact_person_id=contact.get("person_id"), contact_name=contact["name"],
                      contact_title=contact.get("title"), contact_linkedin=contact.get("linkedin"),
                      contact_source="linkedin" if contact.get("linkedin") else "manual",
                      contact_email=contact["email"] if verified else None,
                      email_status="verified" if verified else None, email_method=None, email_source=None)
    elif contact and same and contact.get("title") and not lead["contact_title"]:
        fields["contact_title"] = contact["title"]
    conn.execute(f"UPDATE leads SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                 (*fields.values(), lead["id"]))
    conn.commit()
    return lead["id"]
#--------------------------------------------------------------#

# Clear the handled rows; put a note next to rows that couldn't be used
def tidy_tab(ws, done_rows: set[int], notes: dict[int, str]) -> None:
    updates = [{"range": f"A{r}:{NOTE_COL}{r}", "values": [[""] * len(HEADER)]} for r in sorted(done_rows)]
    updates += [{"range": f"{NOTE_COL}{r}", "values": [[note]]} for r, note in notes.items()]
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
#--------------------------------------------------------------#

# Read the tab and turn every row into a lead. Returns the lead ids, for the crawler to do first.
def run_lookups(conn, cfg, client_id: int) -> list[int]:
    ws = open_tab(cfg)
    if ws is None:
        return []
    rows, notes = read_rows(ws)
    lead_ids, done_rows = [], set()
    for r in rows:
        print(f"  manual lookup: {' | '.join(str(v) for v in (r['link'], r['domain'], r['name']) if v)}")
        contact, company = None, r["domain"]
        if r["link"]:
            existing = conn.execute("SELECT * FROM people WHERE client_id = ? AND linkedin_url = ?",
                                    (client_id, r["link"])).fetchone()
            known = existing and existing["full_name"] and (existing["company_name"] or r["domain"])
            # The paid profile search only runs when the row doesn't give us what we need
            profile = {} if known or (r["name"] and r["domain"]) else resolve_profile(client_id, r["link"])
            profile = {**profile, **{k: v for k, v in (("full_name", r["name"]), ("title", r["title"])) if v}}
            person = save_person(conn, client_id, r["link"], profile)
            company = person["company_name"] or r["domain"]
            contact = {"name": person["full_name"], "title": person["title"], "linkedin": r["link"],
                       "person_id": person["id"], "email": person["email"], "email_status": person["email_status"]}
        elif r["name"]:
            contact = {"name": r["name"], "title": r["title"]}
        if not company:
            notes[r["row"]] = "company not found for this profile: add the domain in column B"
            continue
        lead_ids.append(save_lead(conn, client_id, company, r["domain"], contact))
        done_rows.add(r["row"])

    tidy_tab(ws, done_rows - set(notes), notes)
    return list(dict.fromkeys(lead_ids))
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
