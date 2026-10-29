#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
from datetime import datetime, timezone 
from job_alerts.core.config import load_config 
from job_alerts.core.db import get_conn 
from job_alerts.sources import ba_jobs 
#--------------------------------------------------------------#

# Collects job listings and inserts into database
def collect(client: str) -> None:
    cfg = load_config(client)
    days = cfg.job_alerts["lookback_days"]
    excludes = [x.lower() for x in cfg.listening.job_exclude_keywords]

    conn = get_conn()
    client_id = conn.execute("SELECT id FROM clients WHERE name = ?", (client,)).fetchone()["id"]

    fetched = new = 0
    for keyword in cfg.listening.job_keywords:
        for p in ba_jobs.fetch(keyword, days=days):
            fetched += 1
            title = (p["title"] or "").lower()
            if any(x in title for x in excludes):
                continue
            cur = conn.execute(
                """
                INSERT INTO job_postings 
                (client_id, source, external_id, url, title, company_name, 
                location, country, posted_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (client_id, source, external_id) DO NOTHING
                """,
                (client_id, p["source"], p["external_id"], p["url"], p["title"], p["company_name"], p["location"], p["country"], p["posted_at"],
                 datetime.now(timezone.utc).isoformat()
            ))
            new += cur.rowcount 
    conn.commit()
    conn.close()
    print(f"[{client}] fetched {fetched} postings, {new} new.")
#--------------------------------------------------------------#
#------------------end-of-code---------------------------------#