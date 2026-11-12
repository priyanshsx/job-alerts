#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.names import normalize_name
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
#--------------------------------------------------------------#

def _add_source(sources: str | None, source: str) -> str:
    items = [s.strip() for s in (sources or "").split(",") if s.strip()]
    if source not in items:
        items.append(source)
    return ", ".join(items)
#--------------------------------------------------------------#

# Creates or updates one lead per company from priority 1-2 job postings
def build_leads(client: str) -> None:
    conn = get_conn()
    client_id = get_client_id(conn, client)
    rows = conn.execute(
        "SELECT * FROM job_postings WHERE client_id = ? AND is_relevant = 1 "
        "AND priority IS NOT NULL AND priority <= 2 ORDER BY posted_at",
        (client_id,),
    ).fetchall()

    new = updated = 0
    for r in rows:
        key = normalize_name(r["company_name"])
        if not key:
            continue
        lead = conn.execute(
            "SELECT * FROM leads WHERE client_id = ? AND name_normalized = ?",
            (client_id, key),
        ).fetchone()
        signal = f"Hiring: {r['title']}"
        #--------------------------------------------------------------#

        if lead is None:
            conn.execute(
                """INSERT INTO leads (client_id, company_name, name_normalized, country, sources,
                   latest_signal, latest_signal_at, priority, language, company_size, links,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (client_id, r["company_name"], key, r["country"], "job_alert", signal,
                 r["posted_at"], r["priority"], r["language_requirement"], r["company_size"],
                 r["url"], _now(), _now()),
            )
            new += 1
            continue
        #--------------------------------------------------------------#

        # Existing lead: update engine fields only, never the team-owned ones
        is_newer = (r["posted_at"] or "") > (lead["latest_signal_at"] or "")
        if lead["on_team_list"]:
            signal = f"On your list, now hiring: {r['title']}"
        conn.execute(
            """UPDATE leads SET sources = ?, priority = ?, latest_signal = ?, latest_signal_at = ?,
               language = ?, company_size = ?, links = ?, updated_at = ? WHERE id = ?""",
            (_add_source(lead["sources"], "job_alert"),
             min(p for p in (lead["priority"], r["priority"]) if p is not None),
             signal if is_newer else lead["latest_signal"],
             r["posted_at"] if is_newer else lead["latest_signal_at"],
             r["language_requirement"] if is_newer else lead["language"],
             r["company_size"] if is_newer else lead["company_size"],
             r["url"] if is_newer else lead["links"],
             _now(), lead["id"]),
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"[{client}] leads: {new} new, {updated} updated")

    # Requests found by content-suggester (Requests tab) become priority 1 leads
    from job_alerts.request_leads import import_requests
    import_requests(client)

    # Job ads spotted in posts (content-suggester) become leads too (replaces the old Hiring tab)
    from job_alerts.hiring_leads import import_hiring_posts
    import_hiring_posts(client)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#