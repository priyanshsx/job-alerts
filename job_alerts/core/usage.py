#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/core/usage.py
# Purpose: log paid API calls other than the LLM (searches) to api_calls, for the cost
#          dashboard. The CLI sets the client and command once; sources just call log_call().
#          Prices come from .env (defaults in brackets):
#            UNOBLOX_SEARCH_USD_PER_RESULT (0.005)   Unoblox search bills per result returned
#            SERPER_USD_PER_CREDIT (0.001)           Serper bills 1 credit per 10 results
#--------------------------------------------------------------#

# Imports libraries
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from job_alerts.core.db import ROOT, get_conn, get_client_id
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
_context = {"client": None, "task": None}
#--------------------------------------------------------------#

def set_context(client: str | None, task: str | None) -> None:
    _context.update(client=client, task=task)

def unoblox_price() -> float:
    return float(os.getenv("UNOBLOX_SEARCH_USD_PER_RESULT") or 0.005)

def serper_price() -> float:
    return float(os.getenv("SERPER_USD_PER_CREDIT") or 0.001)
#--------------------------------------------------------------#

# Record one paid call. Never lets a logging problem stop the run.
def log_call(service: str, units: int, cost_usd: float) -> None:
    try:
        conn = get_conn()
        try:
            client_id = get_client_id(conn, _context["client"]) if _context["client"] else None
            conn.execute("INSERT INTO api_calls (client_id, service, task, units, cost_usd, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (client_id, service, _context["task"], units, cost_usd,
                          datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"  (couldn't log {service} usage: {e})")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
