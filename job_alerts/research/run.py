#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/research/run.py
# Purpose: the research command. For each lead that has an email (and is due), reads the company's
#          own website, keeps updates from the last lookback_days and saves notes for the ones that
#          match the client's events. Runs again every rerun_days.
#            python3 -m job_alerts research --client vizcorn            (all due leads, 8 minutes)
#            python3 -m job_alerts research --client vizcorn --lead 135 (one lead, even if not due)
#            python3 -m job_alerts research --client vizcorn --rematch  (no fetching: apply changed
#                                                                        keywords to pages already read)
#          Pages are shared by all clients (they're about the company); notes are per client.
#--------------------------------------------------------------#

# Imports libraries
import time
from datetime import datetime, timedelta, timezone
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.research import pages as site_pages
from job_alerts.research import rules
#--------------------------------------------------------------#

# Global variables
REUSE_DAYS = 7                         # a page read in the last week isn't fetched again
#--------------------------------------------------------------#

def _now() -> datetime:
    return datetime.now(timezone.utc)

def settings(cfg) -> dict:
    r = dict(getattr(cfg, "research", None) or {})
    r.setdefault("enabled", False)
    r.setdefault("lookback_days", 90)
    r.setdefault("rerun_days", 14)
    r.setdefault("max_pages", 15)
    r.setdefault("half_life_days", 30)
    return r
#--------------------------------------------------------------#

# Leads with an email whose research is due
def due_leads(conn, client_id: int) -> list[int]:
    now = _now().isoformat()
    return [r["id"] for r in conn.execute(
        """SELECT l.id FROM leads l LEFT JOIN research_runs r ON r.lead_id = l.id
           WHERE l.client_id = ? AND l.domain IS NOT NULL
             AND (l.contact_email IS NOT NULL OR l.extra_email IS NOT NULL)
             AND COALESCE(l.status, '') NOT IN ('not a fit')
             AND (r.next_at IS NULL OR r.next_at <= ?)
           ORDER BY l.priority, l.id DESC""", (client_id, now))]
#--------------------------------------------------------------#

def _home_url(conn, domain: str) -> str:
    row = conn.execute("SELECT home_url FROM site_crawls WHERE domain = ?", (domain,)).fetchone()
    return (row and row["home_url"]) or f"https://www.{domain}/"

def _store_pages(conn, domain: str, found: list[dict]) -> None:
    now = _now().isoformat()
    for p in found:
        conn.execute(
            """INSERT INTO research_pages (domain, url, source, title, published_at, date_source, lang, text, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (url) DO UPDATE SET title = excluded.title, published_at = excluded.published_at,
                 date_source = excluded.date_source, lang = excluded.lang, text = excluded.text,
                 fetched_at = excluded.fetched_at""",
            (domain, p["url"], p["source"], p["title"], p["published_at"], p["date_source"], p["lang"],
             p["text"], now))
    conn.commit()
#--------------------------------------------------------------#

# Rebuild one lead's notes from every page of its company in the lookback window
def rematch_lead(conn, cfg, client_id: int, lead) -> int:
    r = settings(cfg)
    events = rules.compile_events(r.get("events"))
    since = (_now() - timedelta(days=r["lookback_days"])).date().isoformat()
    conn.execute("DELETE FROM research_notes WHERE lead_id = ? AND client_id = ?", (lead["id"], client_id))
    count = 0
    for page in conn.execute("SELECT * FROM research_pages WHERE domain = ? AND published_at >= ?",
                             (lead["domain"], since)).fetchall():
        for m in rules.match_page(dict(page), events, r["half_life_days"])[:2]:     # at most 2 events per page
            conn.execute(
                """INSERT INTO research_notes (client_id, lead_id, page_id, event, points, matched, snippet, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (lead_id, page_id, event) DO NOTHING""",
                (client_id, lead["id"], page["id"], m["event"], m["points"], m["matched"], m["snippet"],
                 _now().isoformat()))
            count += 1
    conn.commit()
    return count

# Read one lead's website and save its notes. Returns a one-line summary.
def research_lead(conn, cfg, client_id: int, lead_id: int) -> str:
    r = settings(cfg)
    lead = conn.execute("SELECT * FROM leads WHERE id = ? AND client_id = ?", (lead_id, client_id)).fetchone()
    if not lead:
        return "not found"
    if not lead["domain"]:
        status, read_count = "no website", 0
    else:
        since = (_now() - timedelta(days=r["lookback_days"])).date()
        recent = {row["url"] for row in conn.execute(
            "SELECT url FROM research_pages WHERE domain = ? AND fetched_at >= ?",
            (lead["domain"], (_now() - timedelta(days=REUSE_DAYS)).isoformat()))}
        result = site_pages.read_site(_home_url(conn, lead["domain"]), since, int(r["max_pages"]), skip_urls=recent)
        _store_pages(conn, lead["domain"], result["pages"])
        status = result["status"]
        read_count = conn.execute("SELECT COUNT(*) FROM research_pages WHERE domain = ? AND published_at >= ?",
                                  (lead["domain"], since.isoformat())).fetchone()[0]
    notes = rematch_lead(conn, cfg, client_id, lead) if lead["domain"] else 0
    if status == "ok" and not notes:
        status = "no updates"
    next_at = (_now() + timedelta(days=r["rerun_days"])).isoformat()
    conn.execute(
        """INSERT INTO research_runs (lead_id, client_id, status, pages_read, notes, ran_at, next_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (lead_id) DO UPDATE SET status = excluded.status, pages_read = excluded.pages_read,
             notes = excluded.notes, ran_at = excluded.ran_at, next_at = excluded.next_at""",
        (lead_id, client_id, status, read_count, notes, _now().isoformat(), next_at))
    conn.commit()
    return f"{status}: {read_count} recent pages, {notes} notes"
#--------------------------------------------------------------#

def run(client: str, lead_id: int | None = None, minutes: float = 8, rematch: bool = False) -> None:
    cfg = load_config(client)
    r = settings(cfg)
    if not r["enabled"] and lead_id is None:
        print(f"[{client}] research is off (research.enabled in the config)")
        return
    conn = get_conn()
    client_id = get_client_id(conn, client)
    if rematch:
        leads = conn.execute("SELECT l.* FROM leads l JOIN research_runs r ON r.lead_id = l.id "
                             "WHERE l.client_id = ?", (client_id,)).fetchall()
        total = sum(rematch_lead(conn, cfg, client_id, l) for l in leads)
        print(f"[{client}] research rematch: {len(leads)} leads, {total} notes")
        conn.close()
        return
    ids = [lead_id] if lead_id else due_leads(conn, client_id)
    deadline = time.time() + minutes * 60
    done = 0
    for i in ids:
        if time.time() >= deadline:
            break
        name = conn.execute("SELECT company_name FROM leads WHERE id = ?", (i,)).fetchone()
        try:
            line = research_lead(conn, cfg, client_id, i)
        except Exception as e:                   # one bad site never stops the run
            conn.rollback()
            line = f"error: {type(e).__name__}: {str(e)[:150]}"
        print(f"[{client}] {name and name['company_name']}: {line}")
        done += 1
    conn.close()
    print(f"[{client}] research: {done} leads, {len(ids) - done} still due ({_now():%Y-%m-%d %H:%M} UTC)")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
