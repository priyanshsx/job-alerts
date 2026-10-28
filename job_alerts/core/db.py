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

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    return conn
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#