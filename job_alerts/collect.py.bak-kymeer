#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/collect.py
# Purpose: collect job postings from the client's sources and store the ones that pass the
#          title, keyword, agency and company filters.
#          Sources (listening.job_sources in the config):
#            ba_jobs        German Federal Employment Agency (one search per keyword)
#            ats_search     company job boards + LinkedIn jobs via Google (one search per role per site)
#            remote_boards  Remotive + We Work Remotely (fetched once, then filtered by title)
#--------------------------------------------------------------#

# Imports Libraries
from datetime import datetime, timezone
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.sources import ats_search, ba_jobs, remote_boards
#--------------------------------------------------------------#

# All postings from one source, for this client's keywords
def _fetch(source: str, cfg, days: int) -> list[dict]:
    keywords = cfg.listening.job_keywords
    if source == "ba_jobs":
        return [p for k in keywords for p in ba_jobs.fetch(k, days=days)]
    if source == "ats_search":                      # its own keywords if set (e.g. English + local terms)
        ats_keywords = cfg.listening.ats_keywords or keywords
        groups = cfg.listening.job_market_groups or [cfg.listening.job_markets]
        return [p for k in ats_keywords for g in groups for p in ats_search.fetch(k, g, days=days)]
    if source == "remote_boards":
        return remote_boards.fetch(days=days)
    raise ValueError(f"Unknown job source {source!r}. Allowed: ba_jobs, ats_search, remote_boards")
#--------------------------------------------------------------#

# Collects job listings and inserts into database
def collect(client: str) -> None:
    cfg = load_config(client)
    days = cfg.job_alerts["lookback_days"]
    excludes = [x.lower() for x in cfg.listening.job_exclude_keywords]
    must_contain = [x.lower() for x in cfg.listening.job_title_must_contain]
    agencies = [x.lower() for x in cfg.listening.job_agency_names]
    blocked = [x.lower() for x in cfg.listening.job_exclude_companies]

    conn = get_conn()
    client_id = get_client_id(conn, client)

    fetched = new = 0
    for source in cfg.listening.job_sources:
        try:
            postings = _fetch(source, cfg, days)
        except Exception as e:                       # one broken source must not stop the rest
            print(f"  {source} failed: {e}")
            continue
        source_new = 0
        for p in postings:
            fetched += 1
            title = (p["title"] or "").lower()
            company = (p["company_name"] or "").lower()
            if any(x in title for x in excludes):
                continue
            if must_contain and not any(x in title for x in must_contain):
                continue
            if any(a in company for a in agencies):
                continue
            if any(b in company for b in blocked):
                continue
            cur = conn.execute(
                """
                INSERT INTO job_postings
                (client_id, source, external_id, url, title, company_name,
                location, country, posted_at, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (client_id, source, external_id) DO NOTHING
                """,
                (client_id, p["source"], p["external_id"], p["url"], p["title"], p["company_name"],
                 p["location"], p["country"], p["posted_at"], p.get("description"),
                 datetime.now(timezone.utc).isoformat()),
            )
            source_new += cur.rowcount
        new += source_new
        print(f"  {source}: {len(postings)} postings, {source_new} new after filters")
    conn.commit()
    conn.close()
    print(f"[{client}] fetched {fetched} postings, {new} new.")
#--------------------------------------------------------------#
#------------------end-of-code---------------------------------#
