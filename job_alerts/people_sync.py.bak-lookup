#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/people_sync.py
# Purpose: two-way sync between the people table and the People tab of the client's Google Sheet.
#          Pull: your Status and Note go into the database.
#          Push: new people are appended; changed engine cells are updated.
#          Columns are found by header name. Your columns are never overwritten.
#--------------------------------------------------------------#

# Imports libraries
from gspread.utils import rowcol_to_a1
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.sheets import open_worksheet
#--------------------------------------------------------------#

# Global variables: sheet header -> people table column
ENGINE_COLUMNS = {                 # written by the tool; don't edit these in the sheet
    "Person ID": "id",
    "Name": "full_name",
    "Title": "title",
    "Company": "company_name",
    "Location": "location",
    "LinkedIn": "linkedin_url",
    "Why connect": "reason",
    "Priority": "priority",
    "Found via": "source",
    "Found on": "created_at",
    "Email": "email",                      # filled by the contacts command
    "Email status": "email_status",
}
TEAM_COLUMNS = {                   # edited by you; the tool only reads these
    "Status": "connection_status", # to connect, requested, connected, conversation, skip
    "Note": "note",
    "Last updated": "last_updated",
    "Find email": "find_email",            # Monday tick: find this person's email
}
ALL_HEADERS = list(ENGINE_COLUMNS) + list(TEAM_COLUMNS)
SOURCE_LABELS = {"job_alerts_company": "company hiring now", "title_search": "role search",
                 "lead_contact": "contact for a lead",
                 "requester": "asked for help"}
#--------------------------------------------------------------#

# Format one engine value for the sheet
def _engine_value(header: str, person) -> str:
    value = person[ENGINE_COLUMNS[header]]
    if value is None:
        return ""
    if header == "Found on":
        return str(value)[:10]
    if header == "Found via":
        return SOURCE_LABELS.get(value, value)
    return str(value)
#--------------------------------------------------------------#

# Add missing headers at the end of row 1; never rename or move existing ones
def _ensure_headers(ws, values: list[list[str]]) -> list[str]:
    headers = values[0] if values else []
    missing = [h for h in ALL_HEADERS if h not in headers]
    if missing:
        headers = headers + missing
        if len(headers) > ws.col_count:
            ws.add_cols(len(headers) - ws.col_count)
        ws.update(range_name="A1", values=[headers])
    return headers
#--------------------------------------------------------------#

# Two-way sync for one client's People tab
def people_sync(client: str) -> None:
    cfg = load_config(client)
    sheets_cfg = getattr(cfg, "sheets", None)
    if not sheets_cfg or not sheets_cfg.get("spreadsheet_id"):
        print(f"[{client}] no sheets.spreadsheet_id in config, skipping people sync")
        return

    tab = sheets_cfg.get("people_tab", "People")
    ws = open_worksheet(sheets_cfg["spreadsheet_id"], tab)
    values = ws.get_all_values()                        # one read for the whole tab
    headers = _ensure_headers(ws, values)
    col = {h: i for i, h in enumerate(headers)}
    rows = values[1:] if values else []

    def cell(row: list[str], header: str) -> str:
        i = col[header]
        return row[i].strip() if i < len(row) else ""

    in_sheet = {}
    for row_number, row in enumerate(rows, start=2):
        person_id = cell(row, "Person ID")
        if person_id.isdigit():
            in_sheet[int(person_id)] = (row_number, row)
    #--------------------------------------------------------------#

    conn = get_conn()
    client_id = get_client_id(conn, client)

    # 1. Pull: copy your columns into the database
    for person_id, (_, row) in in_sheet.items():
        conn.execute(
            "UPDATE people SET connection_status = ?, note = ?, last_updated = ?, find_email = ? "
            "WHERE id = ? AND client_id = ?",
            (cell(row, "Status").lower() or None, cell(row, "Note") or None,
             cell(row, "Last updated") or None,
             int(cell(row, "Find email").upper() in ("TRUE", "YES", "1", "X")),
             person_id, client_id),
        )
    conn.commit()

    people = conn.execute(
        "SELECT * FROM people WHERE client_id = ? ORDER BY created_at DESC, priority",
        (client_id,),
    ).fetchall()
    #--------------------------------------------------------------#

    # 2. Push updates: rewrite only engine cells whose value changed
    updates = []
    for person in people:
        if person["id"] not in in_sheet:
            continue
        row_number, row = in_sheet[person["id"]]
        for header in ENGINE_COLUMNS:
            new_value = _engine_value(header, person)
            if cell(row, header) != new_value:
                updates.append({"range": rowcol_to_a1(row_number, col[header] + 1),
                                "values": [[new_value]]})
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    #--------------------------------------------------------------#

    # 3. Push new people: append rows, with Status set to "to connect"
    new_rows = []
    for person in people:
        if person["id"] in in_sheet:
            continue
        row = [""] * len(headers)
        for header in ENGINE_COLUMNS:
            row[col[header]] = _engine_value(header, person)
        row[col["Status"]] = "to connect"
        new_rows.append(row)
    if new_rows:
        ws.insert_rows(new_rows, row=2, value_input_option="RAW")      # newest at the top, under the header

    conn.close()
    print(f"[{client}] people sync: pulled {len(in_sheet)} rows, updated {len(updates)} cells, "
          f"added {len(new_rows)} people (tab '{tab}')")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
