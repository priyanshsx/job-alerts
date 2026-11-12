#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/hiring_leads.py
# Purpose: turn job ads spotted in posts (found by content-suggester) into leads, replacing the
#          old Hiring tab. Reads content-suggester's database directly (read-only): no AI calls,
#          no searches, no cost.
#          Only posts classified since the "hiring company" field exists are imported (older ones
#          rarely name a company). Named company -> priority 2; no company (usually a recruiter)
#          -> priority 3. One row per company, merged with existing leads; nothing imported twice.
#--------------------------------------------------------------#

# Imports libraries
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from job_alerts.core.config import load_config
from job_alerts.core.db import ROOT, get_conn, get_client_id
from job_alerts.core.names import normalize_name
#--------------------------------------------------------------#

# Global variables
DEFAULT_SUGGESTER_DB = ROOT.parent.parent / "content-suggester" / "content-suggester-repo" / "data" / "suggester.db"
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _add_source(sources: str | None, source: str) -> str:
    items = [s.strip() for s in (sources or "").split(",") if s.strip()]
    if source not in items:
        items.append(source)
    return ", ".join(items)

def _suggester_db() -> Path:
    return Path(os.getenv("CONTENT_SUGGESTER_DB", str(DEFAULT_SUGGESTER_DB)))
#--------------------------------------------------------------#

# New job posts for this client from content-suggester's database
def read_hiring_posts(client: str) -> list[dict]:
    path = _suggester_db()
    if not path.exists():
        print(f"[{client}] hiring posts: content-suggester database not found at {path} "
              "(set CONTENT_SUGGESTER_DB in .env), skipping")
        return []
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        row = src.execute("SELECT id FROM clients WHERE name = ?", (client,)).fetchone()
        if not row:
            return []
        rows = src.execute(
            """SELECT i.id AS item_id, i.platform, i.url, i.author_name, i.author_handle, i.text,
                      COALESCE(i.posted_at, substr(i.first_seen_at, 1, 10)) AS posted_at,
                      c.hiring_company, c.region
               FROM items i JOIN classifications c ON c.item_id = i.id
               WHERE i.client_id = ? AND c.is_job_post = 1 AND c.hiring_company IS NOT NULL
               ORDER BY i.first_seen_at""", (row["id"],)).fetchall()
        return [dict(r) for r in rows]
    finally:
        src.close()
#--------------------------------------------------------------#

# Import new hiring posts as leads
def import_hiring_posts(client: str) -> None:
    cfg = load_config(client)
    sheets_cfg = getattr(cfg, "sheets", None) or {}
    if sheets_cfg.get("hiring_to_leads", True) is False:
        return                                         # e.g. Quartermaster: job posts aren't partner leads
    posts = read_hiring_posts(client)
    if not posts:
        return

    conn = get_conn()
    client_id = get_client_id(conn, client)
    new = updated = 0
    for post in posts:
        if conn.execute("SELECT 1 FROM imported_hiring_posts WHERE client_id = ? AND item_id = ?",
                        (client_id, post["item_id"])).fetchone():
            continue
        company = (post["hiring_company"] or "").strip()
        poster = post["author_name"] or post["author_handle"] or ""
        platform = {"linkedin": "LinkedIn", "sap_community": "SAP Community", "reddit": "Reddit"}.get(
            post["platform"], post["platform"])
        key = normalize_name(company) or f"hiring post {post['item_id']}"
        display = company or (f"Hiring post by {poster}" if poster else f"Hiring post {post['item_id']}")
        priority = 2 if company else 3
        text = " ".join((post["text"] or "").split())
        signal = f"Hiring post on {platform}: {text[:140]}{'...' if len(text) > 140 else ''}"
        lead = conn.execute("SELECT * FROM leads WHERE client_id = ? AND name_normalized = ?",
                            (client_id, key)).fetchone()

        if lead is None:
            cur = conn.execute(
                """INSERT INTO leads (client_id, company_name, name_normalized, country, sources,
                   latest_signal, latest_signal_at, priority, links, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'hiring_post', ?, ?, ?, ?, ?, ?)""",
                (client_id, display, key, post["region"] or None, signal, post["posted_at"],
                 priority, post["url"], _now(), _now()))
            lead_id = cur.lastrowid
            new += 1
        else:
            is_newer = (post["posted_at"] or "") > (lead["latest_signal_at"] or "")
            conn.execute(
                """UPDATE leads SET sources = ?, priority = ?, latest_signal = ?, latest_signal_at = ?,
                   links = ?, updated_at = ? WHERE id = ?""",
                (_add_source(lead["sources"], "hiring_post"),
                 min(p for p in (lead["priority"], priority) if p is not None),
                 signal if is_newer else lead["latest_signal"],
                 post["posted_at"] if is_newer else lead["latest_signal_at"],
                 post["url"] if is_newer else lead["links"], _now(), lead["id"]))
            lead_id = lead["id"]
            updated += 1
        conn.execute("INSERT INTO imported_hiring_posts (client_id, item_id, lead_id, created_at) "
                     "VALUES (?, ?, ?, ?)", (client_id, post["item_id"], lead_id, _now()))
        conn.commit()

    conn.close()
    print(f"[{client}] hiring posts: {new} new leads, {updated} existing leads updated")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
