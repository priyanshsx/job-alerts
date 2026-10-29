#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id 
#--------------------------------------------------------------#

# Main prioritize function 
def prioritize(client: str) -> None:
    cfg = load_config(client)
    rules = cfg.job_alerts["priority_rules"]

    conn = get_conn()
    client_id = get_client_id(conn, client)
    rows = conn.execute(
        "SELECT id, employer_type, role_type FROM job_postings"
        "WHERE client_id = ? AND is_relevant = 1", 
        (client_id,),
    ).fetchall()

    counts = {}
    for r in rows:
        priority = next(
            (rule["priority"] for rule in rules
             if r["employer_type"] in rule["employer_types"]
             and r["role_type"] in rule["role_types"]),
            None,
        )
        conn.execute("UPDATE job_postings SET priority = ? WHERE id = ?", (priority, r["id"]))
        counts[priority] = counts.get(priority, 0) + 1
    conn.commit()
    conn.close()
    print(f"[{client}] priorities: {counts}")
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#