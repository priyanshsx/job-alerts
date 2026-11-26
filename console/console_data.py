#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/console_data.py
# Purpose: everything the console reads and writes. Pages never write SQL themselves.
#          Only the clients in config/console.yaml are ever queried: no other client can show up.
#          Stages are worked out, never stored:
#            Raw leads   no email yet (the enrich crawler keeps trying)
#            Enrichment  an email was found (verified or not)
#            Sent        the team marked it sent (or the sheet says contacted)
#            Follow-up   a follow-up was sent, or the first email has had no reply for N days
#            Replied     a reply was logged (or read from the mailbox)
#          The team's button presses go to lead_events, so a sheet sync can never undo them.
#--------------------------------------------------------------#

# Imports libraries
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import yaml
from job_alerts.core.db import ROOT, get_conn
from job_alerts.costs import _fx, _llm_to_inr
from job_alerts.hiring_leads import _suggester_db
#--------------------------------------------------------------#

# Global variables
STAGES = ["Raw leads", "Enrichment", "Sent", "Follow-up", "Replied"]
STAGE_RULES = {
    "Raw leads": "Add a contact, then run enrichment.",
    "Enrichment": "Email found. Ready for the first email.",
    "Sent": "First email sent. Follow-up 1 is due {first} days later.",
    "Follow-up": "Due follow-ups first. Leads that had all 3 emails wait at the end for a check-in.",
    "Replied": "They wrote back.",
}
EVENTS = {"sent": "First email sent", "follow_up": "Follow-up sent", "replied": "Reply logged",
          "not_fit": "Marked not a fit", "reopened": "Reopened", "contact": "Contact added",
          "enriched": "Enrichment run"}
SHEET_STATUS_SENT = {"contacted", "sent"}
SHEET_STATUS_REPLIED = {"replied", "conversation", "meeting", "meeting booked"}
SHEET_STATUS_NOT_FIT = {"not a fit", "not fit", "rejected", "skip"}
#--------------------------------------------------------------#

@lru_cache(maxsize=1)
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "console.yaml").read_text())

def _conn() -> sqlite3.Connection:
    return get_conn()

def _now() -> datetime:
    return datetime.now(timezone.utc)

def ts(text) -> datetime | None:
    """ISO text from the database -> aware datetime (None if empty or unreadable)."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(str(text)[:10])
        except ValueError:
            try:
                dt = datetime.strptime(str(text).strip(), "%b %d, %Y")    # some job sources: 'Nov 16, 2026'
            except ValueError:
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def ago(text) -> str:
    """'8 minutes ago', '3 days ago'."""
    dt = ts(text)
    if not dt:
        return "never"
    s = (_now() - dt).total_seconds()
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= size:
            n = int(s // size)
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"
#--------------------------------------------------------------#

# The console's clients, as database ids
def client_ids() -> list[int]:
    conn = _conn()
    names = cfg()["clients"]
    rows = conn.execute(f"SELECT id FROM clients WHERE name IN ({','.join('?' * len(names))})", names).fetchall()
    conn.close()
    return [r["id"] for r in rows]

def _in(ids: list) -> str:
    return "(" + ",".join(str(int(i)) for i in ids) + ")" if ids else "(NULL)"

def market_of(country: str | None) -> str:
    code = (country or "").upper()
    for market, codes in cfg()["markets"].items():
        if code in codes:
            return market
    return "Other"

def markets() -> list[str]:
    return list(cfg()["markets"])
#--------------------------------------------------------------#

def _split_links(links: str | None) -> list[str]:
    return [l for l in re.split(r"[\s,;]+", links or "") if l.startswith("http")]

# All leads with their stage (one query per table, joined in Python)
def leads() -> list[dict]:
    ids = client_ids()
    conn = _conn()
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM leads WHERE client_id IN {_in(ids)} ORDER BY latest_signal_at DESC")]
    outreach = {}
    for o in conn.execute(f"SELECT * FROM outreach WHERE client_id IN {_in(ids)} ORDER BY id"):
        outreach[o["lead_id"]] = dict(o)                    # newest email per lead wins
    events = {}
    for e in conn.execute(f"SELECT * FROM lead_events WHERE client_id IN {_in(ids)} ORDER BY created_at, id"):
        events.setdefault(e["lead_id"], []).append(dict(e))
    conn.close()

    days = schedule()
    for lead in rows:
        o = outreach.get(lead["id"]) or {}
        ev = events.get(lead["id"], [])
        lead["events"] = ev
        lead["outreach"] = o
        lead["market"] = market_of(lead["country"])
        lead.update(_stage(lead, o, ev, days))
        signal = ts(lead["latest_signal_at"]) or ts(lead["created_at"])
        lead["signal_iso"] = signal.isoformat() if signal else ""
    rows.sort(key=lambda l: l["signal_iso"], reverse=True)    # dates come in more than one format
    return rows

def schedule() -> dict:
    f = cfg().get("follow_ups") or {}
    return {"first": int(f.get("first_after_days", 7)), "second": int(f.get("second_after_days", 5)),
            "check_in": int(f.get("check_in_after_days", 25))}

def _day(text) -> str | None:
    dt = ts(text)
    return dt.date().isoformat() if dt else None

def event_day(e: dict) -> str:
    return e.get("happened_on") or _day(e["created_at"])

# Where a lead is and what's next. Follow-ups: +first days after the first email, +second days after
# follow-up 1, then a check-in every check_in days after the last email.
def _stage(lead: dict, o: dict, ev: list[dict], days: dict) -> dict:
    sheet = (lead["status"] or "").lower()
    not_fit = sheet in SHEET_STATUS_NOT_FIT
    firsts, follows, replies = [], [], []
    for e in ev:                                           # later events win
        if e["event"] == "not_fit":
            not_fit = True
        elif e["event"] == "reopened":
            not_fit = False
        elif e["event"] == "sent":
            firsts.append(event_day(e))
        elif e["event"] == "follow_up":
            follows.append(event_day(e))
        elif e["event"] == "replied":
            replies.append(event_day(e))
    # Before the console: the old outreach table and the sheet's Status column
    if not firsts and o.get("sent_at"):
        firsts.append(_day(o["sent_at"]))
    if not firsts and sheet in SHEET_STATUS_SENT:
        firsts.append(_day(lead["last_updated"]) or _day(lead["updated_at"]))
    if not follows and o.get("follow_up_sent_at"):
        follows.append(_day(o["follow_up_sent_at"]))
    if not replies and (o.get("replied_at") or sheet in SHEET_STATUS_REPLIED):
        replies.append(_day(o.get("replied_at")) or _day(lead["last_updated"]))
    first = min(filter(None, firsts), default=None)
    follows = sorted(filter(None, follows))
    has_email = bool(lead["contact_email"] or lead["extra_email"])
    out = {"first_email_on": first, "follow_ups_on": follows, "replied_on": max(filter(None, replies), default=None),
           "next_label": None, "next_due": None, "follow_up_due": False, "sent_at": first, "replied_at": None,
           "emails_sent": (1 if first else 0) + len(follows), "order": 9}
    out["replied_at"] = out["replied_on"]
    if not_fit:
        return {**out, "stage": "Not a fit"}
    if replies:
        return {**out, "stage": "Replied"}
    if not first:
        return {**out, "stage": "Enrichment" if has_email else "Raw leads"}
    last = follows[-1] if follows else first
    if len(follows) == 0:
        label, gap = "Follow-up 1", days["first"]
    elif len(follows) == 1:
        label, gap = "Follow-up 2", days["second"]
    else:
        label, gap = "Check-in", days["check_in"]
    due_on = (date.fromisoformat(last) + timedelta(days=gap)).isoformat()
    due = _now().date().isoformat() >= due_on
    out.update(next_label=label, next_due=due_on, follow_up_due=due)
    if not follows and not due:
        return {**out, "stage": "Sent", "order": 0}
    # Follow-up column: due first, then waiting for follow-up 2, then all 3 emails sent (at the end)
    out["order"] = 0 if due else (1 if len(follows) < 2 else 2)
    return {**out, "stage": "Follow-up"}
#--------------------------------------------------------------#

# One lead with everything the detail page shows
def lead_detail(lead_id: int) -> dict | None:
    lead = next((l for l in leads() if l["id"] == lead_id), None)
    if not lead:
        return None
    conn = _conn()
    links = _split_links(lead["links"])
    lead["postings"] = [dict(r) for r in conn.execute(
        f"SELECT title, location, posted_at, url, reason, employer_type, description FROM job_postings "
        f"WHERE client_id = ? AND url IN ({','.join('?' * len(links)) or 'NULL'}) ORDER BY posted_at DESC",
        (lead["client_id"], *links))] if links else []
    lead["crawl"] = None
    lead["site_emails"] = []
    if lead["domain"]:
        crawl = conn.execute("SELECT * FROM site_crawls WHERE domain = ?", (lead["domain"],)).fetchone()
        if crawl:
            lead["crawl"] = dict(crawl)
            try:
                lead["crawl"]["people"] = json.loads(crawl["people"] or "[]")
            except ValueError:
                lead["crawl"]["people"] = []
        lead["site_emails"] = [dict(r) for r in conn.execute(
            "SELECT email, name, is_generic, source_url FROM site_emails WHERE domain = ? ORDER BY is_generic, email",
            (lead["domain"],))]
    lead["sheet"] = sheet_cells("Lead ID", lead_id, conn)
    lead["research"], lead["research_run"] = research(lead_id, conn)
    conn.close()
    return lead

# Research notes for one lead (best first) and its last research run
def research(lead_id: int, conn) -> tuple[list[dict], dict | None]:
    try:
        notes = [dict(r) for r in conn.execute(
            """SELECT n.event, n.points, n.matched, n.snippet, p.url, p.title, p.published_at, p.source, p.lang
               FROM research_notes n JOIN research_pages p ON p.id = n.page_id
               WHERE n.lead_id = ? AND n.client_id IN """ + _in(client_ids()) + """
               ORDER BY n.points DESC, p.published_at DESC""", (lead_id,))]
        run = conn.execute("SELECT * FROM research_runs WHERE lead_id = ?", (lead_id,)).fetchone()
    except sqlite3.OperationalError:                       # migration 018 not run yet
        return [], None
    labels = event_labels()
    seen, out = set(), []
    for n in notes:                                        # one line per page (its best event)
        if n["url"] in seen:
            continue
        seen.add(n["url"])
        n["label"] = labels.get(n["event"], n["event"])
        out.append(n)
    return out[:research_shown()], (dict(run) if run else None)

@lru_cache(maxsize=1)
def _research_cfg() -> dict:
    from job_alerts.core.config import load_config
    merged = {"events": {}, "notes_shown": 5}
    for client in cfg()["clients"]:
        r = getattr(load_config(client), "research", None) or {}
        merged["events"].update(r.get("events") or {})
        merged["notes_shown"] = r.get("notes_shown", merged["notes_shown"])
    return merged

def event_labels() -> dict:
    return {k: v.get("label", k) for k, v in _research_cfg()["events"].items()}

def research_shown() -> int:
    return int(_research_cfg()["notes_shown"])

# Log what the team did. happened_on: the day it really happened (default today).
# "Not a fit" / "Reopen" / "sent" / "replied" also go to the lead's status, so the engine sees them
# (e.g. enrichment skips leads that are not a fit).
LEAD_STATUS = {"not_fit": "not a fit", "reopened": "new", "sent": "contacted", "follow_up": "contacted",
               "replied": "replied"}

def add_event(lead_id: int, event: str, note: str | None = None, happened_on: date | str | None = None) -> None:
    if event not in EVENTS:
        raise ValueError(event)
    conn = _conn()
    row = conn.execute(f"SELECT client_id FROM leads WHERE id = ? AND client_id IN {_in(client_ids())}",
                       (lead_id,)).fetchone()
    if row:
        day = happened_on.isoformat() if isinstance(happened_on, date) else (happened_on or None)
        conn.execute("INSERT INTO lead_events (client_id, lead_id, event, note, created_at, happened_on) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     (row["client_id"], lead_id, event, note or None, _now().isoformat(), day))
        if event in LEAD_STATUS:
            conn.execute("UPDATE leads SET status = ?, last_updated = ? WHERE id = ?",
                         (LEAD_STATUS[event], (day or _now().date().isoformat()), lead_id))
        conn.commit()
    conn.close()

def undo_event(event_id: int) -> None:
    conn = _conn()
    conn.execute(f"DELETE FROM lead_events WHERE id = ? AND client_id IN {_in(client_ids())}", (event_id,))
    conn.commit()
    conn.close()
#--------------------------------------------------------------#

# The contact the team typed (from LinkedIn). Same rules the sheet used: a new name clears the old
# email so the crawler finds this person's, and the website person (if any) moves to second contact.
def save_contact(lead_id: int, name: str, linkedin: str, company: str, title: str = "", domain: str = "") -> str:
    from job_alerts.sources.xray_search import normalize_linkedin_url
    conn = _conn()
    lead = conn.execute(f"SELECT * FROM leads WHERE id = ? AND client_id IN {_in(client_ids())}", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return "lead not found"
    name, linkedin, company, title = name.strip(), linkedin.strip(), company.strip(), title.strip()
    domain = domain.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
    fields = {}
    if company and company != lead["company_name"]:
        fields["company_name"] = company                   # the matching key (name_normalized) stays
    if linkedin:
        fields["contact_linkedin"] = normalize_linkedin_url(linkedin) if "linkedin.com/in/" in linkedin else linkedin
    if title:
        fields["contact_title"] = title
    if name and name.lower() != (lead["contact_name"] or "").strip().lower():
        if lead["contact_email"] and lead["contact_source"] == "website":
            fields.update(extra_name=lead["contact_name"], extra_title=lead["contact_title"],
                          extra_email=lead["contact_email"], extra_email_status=lead["email_status"])
        fields.update(contact_name=name, contact_source="manual", contact_person_id=None, contact_email=None,
                      email_status=None, email_method=None, email_source=None, enrich_next_at=None, enrich_attempts=0)
        if not title:
            fields["contact_title"] = None
    if domain and "." in domain and domain != (lead["domain"] or ""):
        fields.update(domain=domain, domain_status="manual", domain_source="manual", enrich_next_at=None,
                      enrich_attempts=0)
        if lead["contact_email"] and not lead["contact_email"].endswith("@" + domain):
            fields.update(contact_email=None, email_status=None, email_method=None, email_source=None)
    if not fields:
        conn.close()
        return "nothing changed"
    fields["updated_at"] = _now().isoformat()
    conn.execute(f"UPDATE leads SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", (*fields.values(), lead_id))
    conn.execute("INSERT INTO lead_events (client_id, lead_id, event, note, created_at) VALUES (?, ?, 'contact', ?, ?)",
                 (lead["client_id"], lead_id, name or company or domain, _now().isoformat()))
    conn.commit()
    conn.close()
    return "saved"
#--------------------------------------------------------------#

# Enrichment from the console: the same crawler cron runs, for the given leads, now.
# Then research notes for any lead that got an email. Returns one line per lead.
def enrich_now(lead_ids: list[int], progress=None) -> list[str]:
    import fcntl
    from job_alerts import enrich
    from job_alerts.core import usage
    from job_alerts.core.config import load_config
    from job_alerts.research import run as research_run
    enrich.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock = open(enrich.LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return ["The scheduled enrichment is running right now. Try again in a few minutes."]
    conn = _conn()
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM clients")}
    out, cfgs = [], {}
    try:
        for n, lead_id in enumerate(lead_ids, start=1):
            lead = conn.execute(f"SELECT * FROM leads WHERE id = ? AND client_id IN {_in(client_ids())}",
                                (lead_id,)).fetchone()
            if not lead:
                continue
            client = names[lead["client_id"]]
            cfg = cfgs.setdefault(client, load_config(client))
            usage.set_context(client, "enrich")
            if progress:
                progress(n, len(lead_ids), lead["company_name"])
            if lead["enrich_next_at"] == enrich.DONE and lead["contact_email"]:
                conn.execute("UPDATE leads SET enrich_next_at = NULL WHERE id = ?", (lead_id,))   # run again on request
                conn.commit()
            try:
                line = enrich.enrich_lead(conn, cfg, lead["client_id"], lead_id)
            except Exception as e:
                conn.rollback()
                line = f"error: {type(e).__name__}: {str(e)[:150]}"
            after = conn.execute("SELECT contact_email, extra_email FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if (after["contact_email"] or after["extra_email"]) and research_run.settings(cfg)["enabled"]:
                usage.set_context(client, "research")
                try:
                    line += " · research: " + research_run.research_lead(conn, cfg, lead["client_id"], lead_id)
                except Exception as e:
                    conn.rollback()
                    line += f" · research error: {type(e).__name__}"
            conn.execute("INSERT INTO lead_events (client_id, lead_id, event, note, created_at) VALUES (?, ?, 'enriched', ?, ?)",
                         (lead["client_id"], lead_id, line[:300], _now().isoformat()))
            conn.commit()
            out.append(f"{lead['company_name']}: {line}")
    finally:
        conn.close()
        lock.close()
    return out
#--------------------------------------------------------------#

# The console's spreadsheets (only these are ever read from sheet_rows)
@lru_cache(maxsize=1)
def _spreadsheets() -> tuple[str, ...]:
    from job_alerts.core.config import load_config
    out = []
    for client in cfg()["clients"]:
        sid = (getattr(load_config(client), "sheets", None) or {}).get("spreadsheet_id")
        if sid and sid not in out:
            out.append(sid)
    return tuple(out)

# Every sheet cell for one lead or person, from any tab that has its id: {tab: {header: value}}
def sheet_cells(key_header: str, key: int, conn=None) -> dict:
    own = conn is None
    conn = conn or _conn()
    sids = _spreadsheets()
    out = {}
    try:
        for r in conn.execute(
                f"SELECT tab, cells FROM sheet_rows WHERE row_key = ? AND spreadsheet_id IN "
                f"({','.join('?' * len(sids)) or 'NULL'}) ORDER BY tab, row_number", (str(key), *sids)):
            cells = json.loads(r["cells"])
            if key_header in cells:
                out.setdefault(r["tab"], {}).update(cells)
    except sqlite3.OperationalError:                       # migration 017 not run yet
        pass
    if own:
        conn.close()
    return out

def sheet_imported_at() -> str | None:
    conn = _conn()
    sids = _spreadsheets()
    try:
        row = conn.execute(f"SELECT MAX(imported_at) AS at FROM sheet_rows WHERE spreadsheet_id IN "
                           f"({','.join('?' * len(sids)) or 'NULL'})", sids).fetchone()
        return row["at"]
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
#--------------------------------------------------------------#

def people() -> list[dict]:
    conn = _conn()
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM people WHERE client_id IN {_in(client_ids())} ORDER BY created_at DESC, priority")]
    conn.close()
    return rows
#--------------------------------------------------------------#

# Engage: suggested posts from content-suggester, with the team's done / skipped marks
def _suggester():
    path = _suggester_db()
    if not path.exists():
        return None, None
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    row = src.execute("SELECT id FROM clients WHERE name = ?", (cfg()["suggester_client"],)).fetchone()
    return src, (row["id"] if row else None)

def engage_posts() -> list[dict]:
    src, sid = _suggester()
    if not src or sid is None:
        return []
    rows = [dict(r) for r in src.execute(
        """SELECT g.item_id, g.week, g.score, g.rank, g.created_at, i.platform, i.url, i.author_name,
                  i.author_handle, i.text, i.posted_at, c.pillar, c.comment_angle, c.has_pain_or_question
           FROM suggestions g JOIN items i ON i.id = g.item_id
           LEFT JOIN classifications c ON c.item_id = i.id
           WHERE g.client_id = ? ORDER BY g.week DESC, g.rank""", (sid,))]
    src.close()
    conn = _conn()
    try:
        acts = {r["item_id"]: r["action"] for r in conn.execute(
            f"SELECT item_id, action FROM engage_actions WHERE client_id IN {_in(client_ids())}")}
    except sqlite3.OperationalError:
        acts = {}
    conn.close()
    seen = set()
    out = []
    for r in rows:
        if r["item_id"] in seen:
            continue
        seen.add(r["item_id"])
        r["action"] = acts.get(r["item_id"])
        r["kind"] = ("Question" if "?" in (r["text"] or "") else "Pain point") if r["has_pain_or_question"] else None
        out.append(r)
    return out

def mark_post(item_id: int, action: str | None) -> None:
    conn = _conn()
    cid = client_ids()[0]
    if action is None:
        conn.execute("DELETE FROM engage_actions WHERE client_id = ? AND item_id = ?", (cid, item_id))
    else:
        conn.execute("INSERT INTO engage_actions (client_id, item_id, action, created_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT (client_id, item_id) DO UPDATE SET action = excluded.action, "
                     "created_at = excluded.created_at", (cid, item_id, action, _now().isoformat()))
    conn.commit()
    conn.close()
#--------------------------------------------------------------#

# When each part of the engine last did something
def last_runs() -> dict:
    ids = client_ids()
    conn = _conn()
    one = lambda sql: conn.execute(sql).fetchone()[0]
    out = {
        "job_search": one(f"SELECT MAX(created_at) FROM job_postings WHERE client_id IN {_in(ids)}"),
        "classified": one(f"SELECT MAX(classified_at) FROM job_postings WHERE client_id IN {_in(ids)}"),
        "new_postings_7d": one(f"SELECT COUNT(*) FROM job_postings WHERE client_id IN {_in(ids)} "
                               f"AND created_at >= '{(_now() - timedelta(days=7)).isoformat()}'"),
        "enrichment": max(filter(None, [
            one(f"SELECT MAX(COALESCE(enriched_at, contact_checked_at)) FROM leads WHERE client_id IN {_in(ids)}"),
            one(f"SELECT MAX(c.crawled_at) FROM site_crawls c JOIN leads l ON l.domain = c.domain "
                f"WHERE l.client_id IN {_in(ids)}")]), default=None),
        "enrich_waiting": one(f"SELECT COUNT(*) FROM leads WHERE client_id IN {_in(ids)} AND contact_email IS NULL "
                              f"AND COALESCE(enrich_next_at, '') NOT LIKE '9999%'"),
        "people": one(f"SELECT MAX(created_at) FROM people WHERE client_id IN {_in(ids)}"),
    }
    conn.close()
    src, sid = _suggester()
    out["posts"] = None
    if src and sid is not None:
        out["posts"] = src.execute("SELECT MAX(first_seen_at) FROM items WHERE client_id = ?", (sid,)).fetchone()[0]
        src.close()
    out["sheet"] = sheet_imported_at()
    return out
#--------------------------------------------------------------#

# Costs in INR: LLM + paid searches + email checks, for the console's clients only
def cost_events() -> list[dict]:
    usd_inr, _ = _fx()
    ids = client_ids()
    conn = _conn()
    out = []
    for r in conn.execute(f"SELECT task, cost_usd, created_at FROM llm_calls WHERE client_id IN {_in(ids)}"):
        out.append({"what": "AI", "task": r["task"], "inr": _llm_to_inr(r["cost_usd"] or 0, usd_inr), "at": r["created_at"]})
    for r in conn.execute(f"SELECT service, task, units, cost_usd, created_at FROM api_calls WHERE client_id IN {_in(ids)}"):
        what = {"serper": "Google searches", "millionverifier": "Email checks"}.get(r["service"], "People searches")
        out.append({"what": what, "task": r["task"], "inr": (r["cost_usd"] or 0) * usd_inr, "at": r["created_at"]})
    conn.close()
    src, sid = _suggester()
    if src and sid is not None:
        for r in src.execute("SELECT task, cost_usd, created_at FROM llm_calls WHERE client_id = ?", (sid,)):
            out.append({"what": "AI", "task": r["task"], "inr": _llm_to_inr(r["cost_usd"] or 0, usd_inr), "at": r["created_at"]})
        try:
            for r in src.execute("SELECT service, cost_usd, created_at FROM api_calls WHERE client_id = ?", (sid,)):
                out.append({"what": "Post searches", "task": r["service"], "inr": (r["cost_usd"] or 0) * usd_inr,
                            "at": r["created_at"]})
        except sqlite3.OperationalError:
            pass
        src.close()
    return out

# Cost per lead: spend before the lead existed is shared by its postings (classification), plus enrichment.
# An estimate: the engine doesn't log which call belonged to which lead.
def cost_per_lead(all_leads: list[dict], events: list[dict]) -> dict:
    lead_side = [e for e in events if e["task"] not in ("thread_classify",) and e["what"] != "Post searches"]
    total = sum(e["inr"] for e in lead_side)
    if not all_leads:
        return {"avg": 0, "max": 0, "min": 0, "max_lead": None, "min_lead": None}
    conn = _conn()
    ids = client_ids()
    postings = conn.execute(f"SELECT COUNT(*) FROM job_postings WHERE client_id IN {_in(ids)} AND classified_at IS NOT NULL").fetchone()[0] or 1
    conn.close()
    sourcing = sum(e["inr"] for e in lead_side if e["task"] in ("classify_posting", "fetch", "describe", "classify", "run"))
    per_posting = sourcing / postings
    enrich = total - sourcing
    enriched = {l["id"] for l in all_leads if l["contact_email"] or (l["enrich_attempts"] or 0) > 0} \
        or {l["id"] for l in all_leads}
    per_enrich = enrich / len(enriched)
    est = []
    for l in all_leads:
        n = max(1, len(_split_links(l["links"])))
        cost = n * per_posting + (per_enrich if l["id"] in enriched else 0)
        est.append((cost, l))
    est.sort(key=lambda x: x[0])
    return {"avg": total / len(all_leads), "max": est[-1][0], "min": est[0][0],
            "max_lead": est[-1][1]["company_name"], "min_lead": est[0][1]["company_name"],
            "per_posting": per_posting}

# Credits left on each account: the total in console.yaml minus what was used since its date.
# Usage is counted for the whole account (it's one balance), but only the number is shown.
def credits_left() -> list[dict]:
    conn = _conn()
    usd_inr, _ = _fx()
    out = []
    for key, c in (cfg().get("credits") or {}).items():
        since = str(c.get("since") or "1970-01-01")
        if c.get("resets_monthly"):
            month_start = _now().strftime("%Y-%m-01")
            since = max(since, month_start)
        if key == "serper":
            used = conn.execute("SELECT COALESCE(SUM(units), 0) FROM api_calls WHERE service = 'serper' AND created_at >= ?",
                                (since,)).fetchone()[0]
        elif key == "millionverifier":
            used = conn.execute("SELECT COUNT(*) FROM email_verifications WHERE checked_at >= ?", (since,)).fetchone()[0]
        elif key == "llm_inr":
            used = sum(_llm_to_inr(r[0] or 0, usd_inr) for r in conn.execute(
                "SELECT cost_usd FROM llm_calls WHERE created_at >= ?", (since,)))
            src, _sid = _suggester()
            if src:
                used += sum(_llm_to_inr(r[0] or 0, usd_inr) for r in src.execute(
                    "SELECT cost_usd FROM llm_calls WHERE created_at >= ?", (since,)))
                src.close()
        elif key == "search_usd":
            used = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM api_calls WHERE service LIKE 'unoblox%' "
                                "AND created_at >= ?", (since,)).fetchone()[0]
        else:
            continue
        total = float(c.get("total") or 0)
        left = max(0.0, total - float(used))
        out.append({"key": key, "label": c.get("label", key), "total": total, "used": float(used), "left": left,
                    "share": (left / total) if total else 0, "since": since, "resets": bool(c.get("resets_monthly"))})
    conn.close()
    return out
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
