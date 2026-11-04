#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
import os
import gspread
from dotenv import load_dotenv
from job_alerts.core.db import ROOT
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
#--------------------------------------------------------------#

# Opens one tab of a Google Sheet with the service account (creates the tab if missing)
def open_worksheet(spreadsheet_id: str, worksheet: str):
    key_file = ROOT / os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "secrets/google_service_account.json")
    if not key_file.exists():
        raise FileNotFoundError(
            f"Google service account key not found at {key_file}. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE in .env or save the key there."
        )
    gc = gspread.service_account(filename=str(key_file))
    spreadsheet = gc.open_by_key(spreadsheet_id)
    try:
        return spreadsheet.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=worksheet, rows=1000, cols=26)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
