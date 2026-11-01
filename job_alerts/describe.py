#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import time 
import httpx
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.sources import ba_jobs 
#--------------------------------------------------------------#

# Global variables
MAX_CHARS = 6000
#--------------------------------------------------------------#

# Fetches full description for postings that don't have one yet 
def describe(client: str) -> None:
    conn = get_conn()
    client_id = get_client_id(conn, client)
    rows = conn.execute(
        "SELECT id, external_id, title FROM job_postings "
        "WHERE client_id = ? AND source = 'ba_jobs' AND description iS NULL",
        (client_id,),
    ).fetchall()
    print(f"[{client}] fetching descriptions for {len(rows)} postings")

    fetched = missing = failed = 0 
    for i, row in enumerate(rows, start=1):
        try:
            text = ba_jobs.fetch_details(row["external_id"])
        except httpx.HTTPError as e:
            failed += 1
            print(f" {i}/{len(rows)} failed: {row['title']} ({e})")
            continue 

        conn.execute(
            "UPDATE job_postings SET description = ? WHERE id = ?",
            ((text or "")[:MAX_CHARS], row["id"])
        )
        conn.commit()
        if text:
            fetched += 1
        else:
            missing += 1

        if i % 10 == 0:
            print(f" {i}/{len(rows)} done")
        time.sleep(1)
    conn.close()
    print(f"[{client}] descriptions: {fetched} fetched, {missing} missing, {failed} failed")
    #--------------------------------------------------------------#
#---------------------end-of-code------------------------------#