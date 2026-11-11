#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/request_leads.py
# Purpose: turn requests (posts where someone asks for help the client offers) into leads.
#          Reads the Requests tab, which content-suggester fills, straight from the client's sheet.
#          Each request becomes a priority 1 lead with the poster as its contact (also added to
#          People). Requests marked "not relevant" are skipped; none is imported twice.
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.names import normalize_name
from job_alerts.core.sheets import open_worksheet
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _add_source(sources: str | None, source: str) -> str:
    items = [s.strip() for s in (sources or "").split(",") if s.strip()]
    if source not in items:
        items.append(source)
    return ", ".join(items)
#--------------------------------------------------------------#

# Read the Requests tab as a list of dicts (header -> cell text)
def read_requests(spreadsheet_id: str, tab: str) -> list[dict]:
    ws = open_worksheet(spreadsheet_id, tab)
    values = ws.get_all_values()
    if not values:
        return []
    headers = values[0]
    rows = []
    for row in values[1:]:
        record = {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(headers)}
        if record.get("Request ID", "").isdigit():
            rows.append(record)
    return rows
#--------------------------------------------------------------#

# Add the poster to People (once), so outreach is tracked there too
def _save_poster(conn, client_id: int, req: dict, company: str) -> int | None:
    profile = req.get("Poster profile", "")
    if "linkedin.com/in/" not in profile:              # only real personal profiles become People rows
        return None
    conn.execute(
        """INSERT INTO people (client_id, full_name, company_name, linkedin_url, source, reason,
           priority, status, created_at)
           VALUES (?, ?, ?, ?, 'requester', ?, 1, 'sent', ?)
           ON CONFLICT (client_id, linkedin_url) DO NOTHING""",
        (client_id, req.get("Poster") or None, company or None, profile,
         f"Asked for help: {req.get('What they need', '')}", _now()))
    return conn.execute("SELECT id FROM people WHERE client_id = ? AND linkedin_url = ?",
                        (client_id, profile)).fetchone()["id"]
#--------------------------------------------------------------#

# Import new requests as leads
def import_requests(client: str) -> None:
    cfg = load_config(client)
    sheets_cfg = getattr(cfg, "sheets", None) or {}
    if not sheets_cfg.get("spreadsheet_id"):
        return
    tab = sheets_cfg.get("requests_tab", "Requests")
    try:
        requests = read_requests(sheets_cfg["spreadsheet_id"], tab)
    except Exception as e:                             # a missing tab must not stop the daily run
        print(f"[{client}] requests: couldn't read the {tab!r} tab ({e}), skipping")
        return

    conn = get_conn()
    client_id = get_client_id(conn, client)
    new = updated = skipped = 0
    for req in requests:
        request_id = int(req["Request ID"])
        if req.get("Status", "").lower() == "not relevant":
            skipped += 1
            continue
        if conn.execute("SELECT 1 FROM leads WHERE client_id = ? AND request_id = ?",
                        (client_id, request_id)).fetchone():
            continue                                   # already imported

        company = req.get("Company", "")
        poster = req.get("Poster", "")
        if poster.startswith("r/"):                    # Reddit: the "poster" is the subreddit, not a person
            community, poster = poster, ""
        else:
            community = ""
        key = normalize_name(company) or f"request {request_id}"
        if company:
            display_company = company
        elif community:
            display_company = f"Reddit request in {community}"
        else:
            display_company = f"{poster} (no company stated)" if poster else f"Request {request_id}"
        signal = f"Asked for help: {req.get('What they need', '')}".strip()
        person_id = _save_poster(conn, client_id, req, company)
        profile = req.get("Poster profile", "") or None
        lead = conn.execute("SELECT * FROM leads WHERE client_id = ? AND name_normalized = ?",
                            (client_id, key)).fetchone()
        #--------------------------------------------------------------#

        if lead is None:
            conn.execute(
                """INSERT INTO leads (client_id, company_name, name_normalized, country, sources,
                   latest_signal, latest_signal_at, priority, links, request_id, contact_person_id,
                   contact_name, contact_linkedin, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'request', ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                (client_id, display_company, key, req.get("Region") or None, signal,
                 req.get("Found on") or None, req.get("Post link") or None, request_id, person_id,
                 poster or None, profile, _now(), _now()))
            new += 1
        else:
            # Company already a lead (e.g. from job alerts): add the request as its newest signal,
            # keep any contact the team already has
            conn.execute(
                """UPDATE leads SET sources = ?, priority = 1, latest_signal = ?, latest_signal_at = ?,
                   links = ?, request_id = ?,
                   contact_person_id = ?, contact_name = ?, contact_linkedin = ?,
                   updated_at = ? WHERE id = ?""",
                (_add_source(lead["sources"], "request"), signal, req.get("Found on") or None,
                 req.get("Post link") or lead["links"], request_id,
                 *((lead["contact_person_id"], lead["contact_name"], lead["contact_linkedin"])
                   if (lead["contact_name"] or lead["contact_linkedin"])        # keep the team's contact
                   else (person_id, poster or None, profile)),
                 _now(), lead["id"]))
            updated += 1
        conn.commit()

    conn.close()
    print(f"[{client}] requests: {new} new leads, {updated} existing leads updated, "
          f"{skipped} marked not relevant")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
