#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: scripts/emails_to_top.py
# Purpose: one-off. Moves every lead whose email the enrich crawler already found to row 2 of the
#          client's Leads tab (from now on the crawler does this by itself for new finds).
#          Run: python3 scripts/emails_to_top.py vizcorn
#--------------------------------------------------------------#

# Imports libraries
import sys
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.sync import sync
#--------------------------------------------------------------#

def main(client: str) -> None:
    conn = get_conn()
    client_id = get_client_id(conn, client)
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM leads WHERE client_id = ? AND email_method IS NOT NULL AND contact_email IS NOT NULL "
        "ORDER BY enriched_at DESC", (client_id,))]
    conn.close()
    print(f"[{client}] moving {len(ids)} leads with crawler emails to the top")
    sync(client, to_top=ids)


if __name__ == "__main__":
    main(sys.argv[1])
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
