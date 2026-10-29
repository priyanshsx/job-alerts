#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

import os 
import sqlite3 
from pathlib import Path 
#--------------------------------------------------------------#

def _find_root() -> Path:
    for folder in Path(__file__).resolve().parents:
        if (folder / "pyproject.toml").exists():
            return folder 
    raise RuntimeError("Couldn't find the repo root (no pyproject.toml) found above db.")
#--------------------------------------------------------------#

ROOT = _find_root()
DB_PATH = Path(os.getenv("JOB_ALERTS_DB_PATH") or ROOT / "data" / "job_alerts.db")
#--------------------------------------------------------------#

# Connects to the database
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    return conn
#--------------------------------------------------------------#

# gets client id 
def get_client_id(conn: sqlite3.Connection, client: str) -> int:
    row = conn.execute("SELECT id FROM clients WHERE name = ?", (client,)).fetchone()
    if row is None:
        raise ValueError(
            f"Client '{client}' not found in the database."
            f"Run: python3 scripts/new_client.py {client}"
        )
    return row["id"]
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#