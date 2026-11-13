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
    "Contact name": "contact_name",        # filled by the contacts command
    "Contact title": "contact_title",
    "Contact LinkedIn": "contact_linkedin",
    "Contact email": "contact_email",
    "Email status": "email_status",
}
TEAM_COLUMNS = {                   # edited by the team; the engine only reads these
    "Status": "status",
    "Owner": "owner",
    "Next step": "next_step",
    "Next step date": "next_step_date",
    "Notes": "notes",
    "Last updated": "last_updated",
    "Find contact": "find_contact",        # Monday tick: find a contact and email for this lead
}
ALL_HEADERS = list(ENGINE_COLUMNS) + list(TEAM_COLUMNS)
#--------------------------------------------------------------#

def _engine_value(header: str, lead) -> str:
    """Format one engine-owned value for the sheet."""
    value = lead[ENGINE_COLUMNS[header]]
    if value is None:
        return ""
    if header == "Signal date":
        return str(value)[:10]
    if header == "On team list":
        return "yes" if value else ""
    return str(value)
#--------------------------------------------------------------#

def _ensure_headers(ws, values: list[list[str]]) -> list[str]:
    """Write missing headers at the end of row 1; never rename or move existing ones."""
    headers = values[0] if values else []
    missing = [h for h in ALL_HEADERS if h not in headers]
    if missing:
        headers = headers + missing
        if len(headers) > ws.col_count:
            ws.add_cols(len(headers) - ws.col_count)
        ws.update(range_name="A1", values=[headers])
    return headers
#--------------------------------------------------------------#

# Two-way sync between the leads table and the client's Google Sheet
def sync(client: str) -> None:
    cfg = load_config(client)
    sheets_cfg = getattr(cfg, "sheets", None)
    if not sheets_cfg or not sheets_cfg.get("spreadsheet_id"):
        print(f"[{client}] no sheets.spreadsheet_id in config, skipping sync")
        return

    ws = open_worksheet(sheets_cfg["spreadsheet_id"], sheets_cfg.get("worksheet", "Leads"))
    values = ws.get_all_values()                       # one read for the whole sheet
    headers = _ensure_headers(ws, values)
    col = {h: i for i, h in enumerate(headers)}
    rows = values[1:] if values else []

    def cell(row: list[str], header: str) -> str:
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
               notes = ?, last_updated = ?, find_contact = ?
               WHERE id = ? AND client_id = ?""",
            (cell(row, "Status") or "new", cell(row, "Owner") or None,
             cell(row, "Next step") or None, cell(row, "Next step date") or None,
             cell(row, "Notes") or None, cell(row, "Last updated") or None,
             int(cell(row, "Find contact").upper() in ("TRUE", "YES", "1", "X")),
             lead_id, client_id),
        )
    conn.commit()
    #--------------------------------------------------------------#

    leads = conn.execute(
        "SELECT * FROM leads WHERE client_id = ? ORDER BY priority, latest_signal_at DESC",
        (client_id,),
    ).fetchall()

    # 2. Push updates: rewrite only engine cells whose value changed
    updates = []
    for lead in leads:
        if lead["id"] not in in_sheet:
            continue
        row_number, row = in_sheet[lead["id"]]
        for header in ENGINE_COLUMNS:
            new_value = _engine_value(header, lead)
            if cell(row, header) != new_value:
                updates.append({
                    "range": rowcol_to_a1(row_number, col[header] + 1),
                    "values": [[new_value]],
                })
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    #--------------------------------------------------------------#

    # 3. Push new leads: append rows for leads not yet in the sheet
    new_rows = []
    for lead in leads:
        if lead["id"] in in_sheet:
            continue
        row = [""] * len(headers)
        for header in ENGINE_COLUMNS:
            row[col[header]] = _engine_value(header, lead)
        row[col["Status"]] = "new"
        new_rows.append(row)
    if new_rows:
        ws.insert_rows(new_rows, row=2, value_input_option="RAW")      # newest at the top, under the header

    conn.close()
    print(f"[{client}] sync: pulled {len(in_sheet)} rows, updated {len(updates)} cells, "
          f"added {len(new_rows)} new leads ({datetime.now(timezone.utc):%H:%M} UTC)")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
