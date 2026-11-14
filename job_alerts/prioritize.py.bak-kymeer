#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
#--------------------------------------------------------------#

# Columns that exclude and priority rules are allowed to check
RULE_COLUMNS = ["employer_type", "role_type", "language_requirement",
                "company_size", "supplies_anchor_customer", "business_model"]
#--------------------------------------------------------------#

def _check_columns(conditions: dict, where: str) -> None:
    """Fail loudly on a typo in the config, instead of silently matching nothing."""
    for col in conditions:
        if col != "priority" and col not in RULE_COLUMNS:
            raise ValueError(f"Unknown column '{col}' in {where}. Allowed: {RULE_COLUMNS}")
#--------------------------------------------------------------#

def _matches(row, conditions: dict) -> bool:
    """True if every listed column has one of the allowed values."""
    return all(row[col] in allowed for col, allowed in conditions.items() if col != "priority")
#--------------------------------------------------------------#

def prioritize(client: str) -> None:
    cfg = load_config(client)
    rules = cfg.job_alerts["priority_rules"]
    exclude = cfg.job_alerts.get("exclude", {})

    _check_columns(exclude, "job_alerts.exclude")
    for rule in rules:
        _check_columns(rule, "job_alerts.priority_rules")

    conn = get_conn()
    client_id = get_client_id(conn, client)
    listening = getattr(cfg, "listening", None)
    blocked = [b.lower() for b in (getattr(listening, "job_exclude_companies", None) or [])]
    rows = conn.execute(
        f"SELECT id, company_name, {', '.join(RULE_COLUMNS)} FROM job_postings "
        "WHERE client_id = ? AND is_relevant = 1",
        (client_id,),
    ).fetchall()

    counts = {}
    for r in rows:
        if any(b in (r["company_name"] or "").lower() for b in blocked):
            priority = None                                   # on the client's exclude list
        elif any(r[col] in values for col, values in exclude.items()):
            priority = None                                   # excluded: never sent
        else:
            priority = next((rule["priority"] for rule in rules if _matches(r, rule)), None)
        conn.execute("UPDATE job_postings SET priority = ? WHERE id = ?", (priority, r["id"]))
        key = priority if priority is not None else "excluded"
        counts[key] = counts.get(key, 0) + 1

    conn.commit()
    conn.close()
    print(f"[{client}] priorities: {counts}")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#