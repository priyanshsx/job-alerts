#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
from gspread.utils import rowcol_to_a1
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.sheets import open_worksheet
#--------------------------------------------------------------#

# Global variables: sheet header -> leads table column
ENGINE_COLUMNS = {                 # filled by the engine; the team should not edit these
    "Lead ID": "id",
    "Company": "company_name",
    "Country": "country",
    "Sources": "sources",
    "Latest signal": "latest_signal",
    "Signal date": "latest_signal_at",
    "Priority": "priority",
    "Language": "language",
    "Size": "company_size",
    "Links": "links",
    "On team list": "on_team_list",
    "Lead type": "lead_type",
    "Contact name": "contact_name",        # filled by contacts / the crawler, or typed by you (then verified)
    "Contact title": "contact_title",
    "Contact LinkedIn": "contact_linkedin",
    "Contact email": "contact_email",
    "Email status": "email_status",
    "Outreach": "outreach_status",         # filled by outreach-draft / outreach
    "Email method": "email_method",        # filled by the enrich crawler: found on site / company format / common format
    "Email source": "email_source",        # the page where the email or its format was seen
    "Domain": "domain",                    # the crawler's domain; type over it to correct it (yours always wins)
}
SECOND_PERSON = {                  # a second person from the website, shown after "; " in the same cell
    "Contact name": "extra_name",
    "Contact title": "extra_title",
    "Contact email": "extra_email",
    "Email status": "extra_email_status",
}
UNCERTAIN = " (uncertain)"
TEAM_COLUMNS = {                   # edited by the team; the engine only reads these
    "Status": "status",
    "Owner": "owner",
    "Next step": "next_step",
    "Next step date": "next_step_date",
    "Notes": "notes",
    "Last updated": "last_updated",
    "Find contact": "find_contact",        # Monday tick: find a contact and email for this lead
    "Reach out": "reach_out",              # Monday tick: draft an outreach email for this lead
}
ALL_HEADERS = list(ENGINE_COLUMNS) + list(TEAM_COLUMNS)
#--------------------------------------------------------------#

def _engine_value(header: str, lead) -> str:
    """Format one engine-owned value for the sheet."""
    value = lead[ENGINE_COLUMNS[header]]
    if header == "Domain" and value and lead["domain_status"] in ("uncertain",):
        return f"{value}{UNCERTAIN}"
    if header in SECOND_PERSON and lead[SECOND_PERSON["Contact email"]]:
        extra = lead[SECOND_PERSON[header]] or ""
        return f"{value or ''}; {extra}" if value else extra
    if value is None:
        return ""
    if header == "Signal date":
        return str(value)[:10]
    if header == "On team list":
        return "yes" if value else ""
    return str(value)
#--------------------------------------------------------------#

def _sheet_value(value: str):
    """A cell read back from the sheet, ready to write again (ticks stay ticks)."""
    return {"TRUE": True, "FALSE": False}.get(value, value)
#--------------------------------------------------------------#

def _ensure_headers(ws, values: list[list[str]], hidden: set[str] = frozenset()) -> list[str]:
    """Write missing headers at the end of row 1; never rename or move existing ones."""
    headers = values[0] if values else []
    missing = [h for h in ALL_HEADERS if h not in headers and h not in hidden]
    if missing:
        first_new = len(headers)
        headers = headers + missing
        if len(headers) > ws.col_count:
            ws.add_cols(len(headers) - ws.col_count)
        ws.update(range_name="A1", values=[headers])
        engine_new = [i for i, h in enumerate(headers) if i >= first_new and h in ENGINE_COLUMNS]
        if engine_new:                               # text columns: drop any checkbox copied from a neighbour
            ws.spreadsheet.batch_update({"requests": [{"setDataValidation": {"range": {
                "sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": i, "endColumnIndex": i + 1}}}
                for i in engine_new]})
    return headers
#--------------------------------------------------------------#

# Two-way sync between the leads table and the client's Google Sheet.
# to_top: lead ids moved to row 2 (e.g. a new email was just found), keeping every cell of their row.
def sync(client: str, to_top: list[int] | None = None) -> None:
    cfg = load_config(client)
    sheets_cfg = getattr(cfg, "sheets", None)
    if not sheets_cfg or not sheets_cfg.get("spreadsheet_id"):
        print(f"[{client}] no sheets.spreadsheet_id in config, skipping sync")
        return

    ws = open_worksheet(sheets_cfg["spreadsheet_id"], sheets_cfg.get("worksheet", "Leads"))
    values = ws.get_all_values()                       # one read for the whole sheet
    hidden = set((sheets_cfg or {}).get("hide_columns") or [])    # columns this client doesn't want
    headers = _ensure_headers(ws, values, hidden)
    col = {h: i for i, h in enumerate(headers)}
    rows = values[1:] if values else []

    def cell(row: list[str], header: str) -> str:
        if header not in col:                        # a hidden (deleted) column reads as empty
            return ""
        i = col[header]
        return row[i].strip() if i < len(row) else ""

    # Map Lead ID -> (sheet row number, row values)
    in_sheet = {}
    for row_number, row in enumerate(rows, start=2):
        lead_id = cell(row, "Lead ID")
        if lead_id.isdigit():
            in_sheet[int(lead_id)] = (row_number, row)
    #--------------------------------------------------------------#

    conn = get_conn()
    client_id = get_client_id(conn, client)

    # 1. Pull: copy the team's columns into the database
    for lead_id, (_, row) in in_sheet.items():
        conn.execute(
            """UPDATE leads SET status = ?, owner = ?, next_step = ?, next_step_date = ?,
               notes = ?, last_updated = ?, find_contact = ?, reach_out = ?
               WHERE id = ? AND client_id = ?""",
            (cell(row, "Status") or "new", cell(row, "Owner") or None,
             cell(row, "Next step") or None, cell(row, "Next step date") or None,
             cell(row, "Notes") or None, cell(row, "Last updated") or None,
             int(cell(row, "Find contact").upper() in ("TRUE", "YES", "1", "X")),
             int(cell(row, "Reach out").upper() in ("TRUE", "YES", "1", "X")),
             lead_id, client_id),
        )
    conn.commit()

    # 1b. A domain typed in the sheet always wins: the crawler starts again with it
    for lead_id, (_, row) in in_sheet.items():
        typed = cell(row, "Domain").lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
        typed = typed.split("/")[0]
        if not typed or typed.endswith(UNCERTAIN.strip()) or "." not in typed:
            continue
        lead = conn.execute("SELECT * FROM leads WHERE id = ? AND client_id = ?", (lead_id, client_id)).fetchone()
        if not lead or typed == (lead["domain"] or ""):
            continue
        fields = {"domain": typed, "domain_status": "manual", "domain_source": "manual",
                  "enrich_next_at": None, "enrich_attempts": 0}
        if lead["contact_email"] and not lead["contact_email"].endswith("@" + typed):
            fields.update(contact_email=None, email_status=None, email_method=None, email_source=None)
        if lead["extra_email"] and not lead["extra_email"].endswith("@" + typed):
            fields.update(extra_name=None, extra_title=None, extra_email=None, extra_email_status=None)
        conn.execute(f"UPDATE leads SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     (*fields.values(), lead_id))
    conn.commit()

    # 1c. A contact typed in the sheet (Contact name, plus Contact title / LinkedIn if you have them)
    #     becomes the lead's contact; the crawler then finds and verifies their email (MillionVerifier only)
    for lead_id, (_, row) in in_sheet.items():
        lead = conn.execute("SELECT * FROM leads WHERE id = ? AND client_id = ?", (lead_id, client_id)).fetchone()
        if not lead:
            continue
        typed = {h: cell(row, h) for h in ("Contact name", "Contact title", "Contact LinkedIn") if h in col}
        if all(typed[h] == _engine_value(h, lead) for h in typed):
            continue                                 # nothing edited
        name = typed.get("Contact name", "").split(";")[0].strip()
        if not name:
            continue                                 # a contact can't be removed here: the engine writes it back
        fields = {}
        if "Contact title" in typed:
            fields["contact_title"] = typed["Contact title"].split(";")[0].strip() or None
        if "Contact LinkedIn" in typed:
            fields["contact_linkedin"] = typed["Contact LinkedIn"].strip() or None
        if name.lower() != (lead["contact_name"] or "").strip().lower():
            if lead["contact_email"] and lead["contact_source"] == "website":   # website person moves to 2nd
                fields.update(extra_name=lead["contact_name"], extra_title=lead["contact_title"],
                              extra_email=lead["contact_email"], extra_email_status=lead["email_status"])
            fields.update(contact_name=name, contact_source="manual", contact_person_id=None,
                          contact_email=None, email_status=None, email_method=None, email_source=None,
                          enrich_next_at=None, enrich_attempts=0)
        if not fields:
            continue
        conn.execute(f"UPDATE leads SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                     (*fields.values(), lead_id))
    conn.commit()
    #--------------------------------------------------------------#

    leads = conn.execute(
        "SELECT * FROM leads WHERE client_id = ? ORDER BY priority, latest_signal_at DESC",
        (client_id,),
    ).fetchall()

    # 2. Push updates: rewrite only engine cells whose value changed
    to_top = [i for i in dict.fromkeys(to_top or []) if i in in_sheet]
    updates = []
    for lead in leads:
        if lead["id"] not in in_sheet or lead["id"] in to_top:
            continue
        row_number, row = in_sheet[lead["id"]]
        for header in (h for h in ENGINE_COLUMNS if h in col):
            new_value = _engine_value(header, lead)
            if cell(row, header) != new_value:
                updates.append({
                    "range": rowcol_to_a1(row_number, col[header] + 1),
                    "values": [[new_value]],
                })
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    #--------------------------------------------------------------#

    # 3. Leads moved to the top: keep their whole row (your columns too), refresh the engine cells,
    #    then remove the old row (bottom first, so row numbers hold)
    by_id = {l["id"]: l for l in leads}
    moved_rows = []
    for lead_id in to_top:
        _, old_row = in_sheet[lead_id]
        row = [_sheet_value(v) for v in (old_row + [""] * len(headers))[:len(headers)]]
        for header in (h for h in ENGINE_COLUMNS if h in col):
            row[col[header]] = _engine_value(header, by_id[lead_id])
        moved_rows.append(row)
    for row_number in sorted((in_sheet[i][0] for i in to_top), reverse=True):
        ws.delete_rows(row_number)
    #--------------------------------------------------------------#

    # 4. Push new leads and the moved ones at row 2 (moved first, then new, newest on top)
    new_rows = []
    for lead in leads:
        if lead["id"] in in_sheet:
            continue
        row = [""] * len(headers)
        for header in (h for h in ENGINE_COLUMNS if h in col):
            row[col[header]] = _engine_value(header, lead)
        row[col["Status"]] = "new"
        new_rows.append(row)
    if moved_rows or new_rows:
        ws.insert_rows(moved_rows + new_rows, row=2, value_input_option="RAW")   # newest at the top

    conn.close()
    print(f"[{client}] sync: pulled {len(in_sheet)} rows, updated {len(updates)} cells, "
          f"moved {len(moved_rows)} to the top, added {len(new_rows)} new leads ({datetime.now(timezone.utc):%H:%M} UTC)")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
