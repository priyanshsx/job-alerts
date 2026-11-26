#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: scripts/import_sheet.py
# Purpose: bring everything in the client's Google Sheet into the database for the console.
#          1. Runs sync / people-sync (config/console.yaml, import:) so the team's columns
#             (Status, Owner, Notes, ticks...) land in the leads and people tables as usual.
#          2. Copies every row of every tab into sheet_rows, so columns the team added by hand
#             (and tabs the engine doesn't know) show up in the console too.
#          Read-only on the sheet apart from what sync itself does. Safe to run as often as you like.
# Run:     python3 scripts/import_sheet.py            (sync first, then copy)
#          python3 scripts/import_sheet.py --no-sync  (copy only)
#--------------------------------------------------------------#

# Imports libraries
import argparse
import json
from datetime import datetime, timezone
import yaml
from job_alerts.core.config import load_config
from job_alerts.core.db import ROOT, get_conn
from job_alerts.core.sheets import open_worksheet
from job_alerts.sync import sync
from job_alerts.people_sync import people_sync
#--------------------------------------------------------------#

# Global variables
KEY_HEADERS = ["Lead ID", "Person ID"]         # a tab with one of these links its rows to leads / people
#--------------------------------------------------------------#

def _console_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "console.yaml").read_text())
#--------------------------------------------------------------#

# Copies every tab of one spreadsheet into sheet_rows (each tab's old copy is replaced)
def copy_spreadsheet(spreadsheet_id: str, first_tab: str) -> None:
    ws = open_worksheet(spreadsheet_id, first_tab)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    for tab in ws.spreadsheet.worksheets():
        values = tab.get_all_values()
        if not values:
            continue
        headers = [h.strip() for h in values[0]]
        key_col = next((headers.index(k) for k in KEY_HEADERS if k in headers), None)
        rows = []
        for row_number, row in enumerate(values[1:], start=2):
            cells = {h: v.strip() for h, v in zip(headers, row) if h and v.strip()}
            if not cells:
                continue
            key = row[key_col].strip() if key_col is not None and key_col < len(row) else None
            rows.append((spreadsheet_id, tab.title, row_number, key or None,
                         json.dumps(cells, ensure_ascii=False), now))
        conn.execute("DELETE FROM sheet_rows WHERE spreadsheet_id = ? AND tab = ?", (spreadsheet_id, tab.title))
        conn.executemany("INSERT INTO sheet_rows (spreadsheet_id, tab, row_number, row_key, cells, imported_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        print(f"  {tab.title}: {len(rows)} rows, {len([h for h in headers if h])} columns")
    conn.close()
#--------------------------------------------------------------#

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-sync", action="store_true", help="copy the sheet without running sync first")
    args = parser.parse_args()
    cfg = _console_cfg()

    if not args.no_sync:
        for client in cfg.get("import", {}).get("sync", []):
            sync(client, force=True)
        for client in cfg.get("import", {}).get("people_sync", []):
            people_sync(client, force=True)

    done = set()
    for client in cfg["clients"]:
        sheets = getattr(load_config(client), "sheets", None) or {}
        sid = sheets.get("spreadsheet_id")
        if not sid or sid in done:
            continue                                   # two clients can share one spreadsheet
        done.add(sid)
        print(f"[{client}] copying spreadsheet {sid[:8]}…")
        copy_spreadsheet(sid, sheets.get("worksheet", "Leads"))


if __name__ == "__main__":
    main()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
