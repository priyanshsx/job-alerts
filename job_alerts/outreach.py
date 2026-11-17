#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/outreach.py
# Purpose: email outreach for leads and requests, with you stepping in three times.
#   outreach-draft  (Monday, after you tick "Reach out" in the Leads tab)
#                   writes a first email + one follow-up per ticked lead that has an email,
#                   into the Outreach tab. You edit if needed and tick "Approve".   <- step 1 and 2
#   outreach        (every 30 minutes, from cron)
#                   reads replies, picks up your approvals, and sends at most ONE email per run,
#                   within the daily limit, on weekdays, in the recipient's working hours.
#                   A reply stops the follow-up. You answer interested replies yourself.  <- step 3
#   Manual mode (outreach.mode: manual, e.g. Vizcorn): nothing is sent by code. Instead, at set
#   hours you get an alert email with the next drafts (subject + body + an "Open in Outlook" link);
#   you send them yourself and tick "Sent by me" in the Outreach tab. Replies: pick a Reply label.
#   Everything (drafts, your edits, sends, replies and their labels) is kept in the database,
#   so templates can be compared later.
#--------------------------------------------------------------#

# Imports libraries
import random
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from gspread.utils import rowcol_to_a1
from pydantic import BaseModel
from job_alerts import outreach_mail
from urllib.parse import quote
from job_alerts.core.config import load_config
from job_alerts.core.email import send_email
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.llm import call_llm
from job_alerts.core.sheets import open_worksheet
from job_alerts.sync import sync
#--------------------------------------------------------------#

# Global variables
COUNTRY_TIMEZONES = {
    "IN": "Asia/Kolkata", "SG": "Asia/Singapore", "AE": "Asia/Dubai", "AU": "Australia/Sydney",
    "US": "America/New_York", "CA": "America/Toronto", "GB": "Europe/London", "UK": "Europe/London",
    "IE": "Europe/Dublin", "PT": "Europe/Lisbon", "DE": "Europe/Berlin", "AT": "Europe/Vienna",
    "CH": "Europe/Zurich", "NL": "Europe/Amsterdam", "BE": "Europe/Brussels", "FR": "Europe/Paris",
    "ES": "Europe/Madrid", "IT": "Europe/Rome", "PL": "Europe/Warsaw", "HU": "Europe/Budapest",
    "CZ": "Europe/Prague", "SE": "Europe/Stockholm", "DK": "Europe/Copenhagen", "NO": "Europe/Oslo",
    "FI": "Europe/Helsinki", "ZA": "Africa/Johannesburg",
}
DEFAULTS = {
    "outreach_tab": "Outreach",
    "daily_limit": 2,                 # first emails + follow-ups, per day (sender's day)
    "min_gap_minutes": 90,            # at least this long between two sends
    "send_hours": [10, 17],           # recipient's local time, Monday to Friday
    "sender_timezone": "Asia/Kolkata",
    "default_timezone": "Asia/Kolkata",   # when the lead's country is unknown
    "follow_up_after_days": 4,        # working days after the first email
    "send_to_risky": False,           # only send to verified emails
    "opt_out_line": 'If this isn\'t relevant, just reply "no" and I won\'t email again.',
    "mode": "auto",                   # auto: the engine sends; manual: alerts only, you send
    "alert_to": [],                   # manual: who gets the alerts
    "alert_hours": [9, 12, 15],       # manual: alert times, Monday to Friday
    "alert_timezone": "Europe/Berlin",
    "per_alert": 2,                   # manual: drafts per alert
    "alert_grace_hours": 3,           # manual: a missed alert (Mac asleep) still goes out this long after
}
REPLY_LABELS = ("interested", "question", "not_now", "not_interested", "unsubscribe", "out_of_office", "other")
SENT_LIKE = ("sent", "followed_up")
#--------------------------------------------------------------#

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _settings(cfg) -> dict:
    return {**DEFAULTS, **(getattr(cfg, "outreach", None) or {})}
#--------------------------------------------------------------#

# LLM answer shapes
class Draft(BaseModel):
    subject: str
    body: str                  # greeting to the ask; no signature, no opt-out line (added by code)
    follow_up: str             # short follow-up body, same rules

class ReplyLabel(BaseModel):
    label: Literal["interested", "question", "not_now", "not_interested", "unsubscribe",
                   "out_of_office", "other"]
    summary: str               # one line, in English
#--------------------------------------------------------------#

KIND_GUIDANCE = {
    "lead": ("They are hiring for a role connected to what the sender offers (the signal below). "
             "Open with that: you saw they're hiring for <role>. Then say how the sender gets them "
             "results now, alongside or before the hire. Don't apply for the job."),
    "request": ("They asked in public for help with something the sender offers (the signal below). "
                "Open with that: you saw their post asking for <what they asked>. Then say plainly "
                "that the sender can help with exactly that."),
}

DRAFT_PROMPT = """Write a short cold email from {sender} to {recipient}.

About the sender: {offer_line}
Proof points (use only these; never invent numbers, clients or results):
{proof_points}

Recipient: {recipient}{title} at {company}
Why now (the signal): {signal}
How to open: {guidance}

Write it the way the sender writes. Example of an email of theirs that worked:
---
{voice_sample}
---

Rules:
- Greeting: "Hi {first_name}," (or "Hello team {company}," if there is no name).
- Straight to the point: the first sentence says why you're writing, naming the signal concretely.
- One sentence on what the sender would do for them, fitted to their situation.
- Then 2 to 4 bullet points ("- ") picked from the proof points that fit this recipient best.
- End with one simple ask: a 15-minute call this week or next, or a one-line reply.
- Under 130 words. Plain text. No links, no emojis, no signature (it is added automatically).
- Never use: {avoid}.
- subject: 3 to 6 words, specific and plain, lower-key than a headline, no "Re:".
- follow_up: 2 or 3 sentences sent 4 working days later in the same thread if there's no reply.
  Add one new, useful point; no guilt ("just bumping this"), no greeting needed beyond "Hi {first_name},".
"""

LABEL_PROMPT = """A prospect replied to a cold email. Label the reply:
interested (wants to talk or know more), question (asks something before deciding),
not_now (maybe later), not_interested, unsubscribe (asks not to be emailed; a bare "no" counts),
out_of_office (automatic absence reply), other.
summary: one short line in English on what they said.

Reply:
{text}"""
#--------------------------------------------------------------#

# The recipient's time zone, from the lead's country code
def _timezone(country: str | None, settings: dict) -> str:
    return COUNTRY_TIMEZONES.get((country or "").strip().upper(), settings["default_timezone"])

def _in_window(tz: str, settings: dict, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(tz))
    start, end = settings["send_hours"]
    return local.weekday() < 5 and start <= local.hour < end

def _working_days_since(iso: str, tz: str, now: datetime) -> int:
    day = datetime.fromisoformat(iso).astimezone(ZoneInfo(tz)).date()
    today = now.astimezone(ZoneInfo(tz)).date()
    count = 0
    while day < today:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count
#--------------------------------------------------------------#

def _blocked(conn, email: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM do_not_contact WHERE email = ?", (email.lower(),)).fetchone())

def _block(conn, client_id: int, email: str, reason: str) -> None:
    conn.execute("INSERT INTO do_not_contact (email, client_id, reason, added_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT (email) DO NOTHING", (email.lower(), client_id, reason, _now().isoformat()))
#--------------------------------------------------------------#

# What the Leads tab's "Outreach" column says for one outreach row
def _lead_status(row) -> str:
    s = row["status"]
    if s == "drafted":
        return "draft ready: approve in Outreach tab"
    if s == "approved":
        return "approved: queued to send"
    if s == "alerted":
        return f"in your alert of {row['alerted_at'][:10]}: send it"
    if s == "follow_up_alerted":
        return f"follow-up in your alert of {row['follow_up_alerted_at'][:10]}: send it"
    if s == "sent":
        return f"sent {row['sent_at'][:10]}"
    if s == "followed_up":
        return f"follow-up sent {row['follow_up_sent_at'][:10]}"
    if s == "replied":
        return f"replied: {row['reply_label']}"
    return s

def _refresh_lead(conn, row) -> None:
    conn.execute("UPDATE leads SET outreach_status = ? WHERE id = ?", (_lead_status(row), row["lead_id"]))
#--------------------------------------------------------------#

# Write one draft for one lead
def _draft(cfg, settings: dict, client_id: int, lead) -> tuple[Draft, str]:
    name = (lead["contact_name"] or "").strip()
    if name and " " not in name and ("-" in name or name.islower()):   # a LinkedIn handle, e.g. "john-iwuozor"
        name = " ".join(w.capitalize() for w in name.split("-") if w.isalpha())
    signal = lead["latest_signal"] or ""
    kind = "request" if signal.lower().startswith("asked for help") else "lead"
    prompt = DRAFT_PROMPT.format(
        sender=settings.get("sender_name", cfg.display_name),
        recipient=name or f"the team at {lead['company_name']}",
        title=f", {lead['contact_title']}" if lead["contact_title"] else "",
        company=lead["company_name"], signal=signal, guidance=KIND_GUIDANCE[kind],
        offer_line=" ".join(settings.get("offer_line", cfg.offer).split()),
        proof_points="\n".join(f"- {p}" for p in settings.get("proof_points", [])),
        voice_sample=settings.get("voice_sample", "").strip(),
        first_name=name.split()[0] if name else "", avoid=", ".join(settings.get("avoid_phrases", [])) or "none")
    return call_llm(f"outreach_draft_{kind}", prompt, Draft, client_id, max_tokens=900), kind
#--------------------------------------------------------------#

# Monday: drafts for leads ticked "Reach out"
def draft_outreach(client: str) -> None:
    sync(client)                                     # read the "Reach out" ticks
    cfg = load_config(client)
    settings = _settings(cfg)
    conn = get_conn()
    client_id = get_client_id(conn, client)
    leads = conn.execute("SELECT * FROM leads WHERE client_id = ? AND reach_out = 1 AND id NOT IN "
                         "(SELECT lead_id FROM outreach WHERE client_id = ?)", (client_id, client_id)).fetchall()
    drafted = 0
    for lead in leads:
        email = (lead["contact_email"] or "").strip().lower()
        if not email:
            status = "needs an email: tick Find contact and run contacts"
        elif lead["email_status"] != "verified" and not settings["send_to_risky"]:
            status = f"email not verified ({lead['email_status']}): not sent"
        elif _blocked(conn, email):
            status = "on the do-not-contact list"
        else:
            status = None
        if status:
            conn.execute("UPDATE leads SET outreach_status = ? WHERE id = ?", (status, lead["id"]))
            conn.commit()
            print(f"  {lead['company_name']}: {status}")
            continue

        draft, kind = _draft(cfg, settings, client_id, lead)
        links = (lead["links"] or "").split()
        conn.execute(
            """INSERT INTO outreach (client_id, lead_id, kind, company, to_email, to_name, signal, link,
               timezone, subject, body, follow_up_body, draft_subject, draft_body, draft_follow_up,
               status, approved, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'drafted', 0, ?, ?)
               ON CONFLICT (client_id, lead_id) DO NOTHING""",
            (client_id, lead["id"], kind, lead["company_name"], email, lead["contact_name"],
             lead["latest_signal"], links[0] if links else None, _timezone(lead["country"], settings),
             draft.subject, draft.body, draft.follow_up, draft.subject, draft.body, draft.follow_up,
             _now().isoformat(), _now().isoformat()))
        row = conn.execute("SELECT * FROM outreach WHERE client_id = ? AND lead_id = ?",
                           (client_id, lead["id"])).fetchone()
        _refresh_lead(conn, row)
        conn.commit()
        drafted += 1
        print(f"  {lead['company_name']}: drafted ({kind}) for {email}")
    conn.close()
    print(f"[{client}] outreach drafts: {drafted} new")
    sync_tab(client)
    sync(client)                                     # show each lead's outreach status
#--------------------------------------------------------------#

# The Outreach tab: one row per lead. You edit Subject / Email / Follow-up and tick Approve.
TAB_ENGINE = {"Outreach ID": "id", "Company": "company", "To": "to_email", "Contact": "to_name",
              "Type": "kind", "Signal": "signal", "Link": "link", "Status": "status",
              "Sent": "sent_at", "Follow-up sent": "follow_up_sent_at", "Reply label": "reply_label",
              "Reply": "reply_text"}
TAB_EDITABLE = {"Subject": "subject", "Email": "body", "Follow-up": "follow_up_body"}
TAB_HEADERS = ["Outreach ID", "Company", "To", "Contact", "Type", "Signal", "Link", "Subject",
               "Email", "Follow-up", "Approve", "Status", "Sent", "Follow-up sent", "Reply label", "Reply"]

MANUAL_TICKS = {"Sent by me": "sent_at", "Follow-up sent by me": "follow_up_sent_at"}

def _tab_headers(settings: dict) -> list[str]:
    if settings["mode"] != "manual":
        return TAB_HEADERS
    i = TAB_HEADERS.index("Status")
    return TAB_HEADERS[:i] + list(MANUAL_TICKS) + TAB_HEADERS[i:]

def _cell_value(header: str, row) -> str:
    value = row[TAB_ENGINE.get(header) or TAB_EDITABLE[header]]
    if value is None:
        return ""
    return str(value)[:16].replace("T", " ") if header in ("Sent", "Follow-up sent") else str(value)

def sync_tab(client: str) -> None:
    cfg = load_config(client)
    settings = _settings(cfg)
    ws = open_worksheet(cfg.sheets["spreadsheet_id"], settings["outreach_tab"])
    values = ws.get_all_values()
    headers = values[0] if values else []
    missing = [h for h in _tab_headers(settings) if h not in headers]
    if missing:
        headers = headers + missing
        if len(headers) > ws.col_count:
            ws.add_cols(len(headers) - ws.col_count)
        ws.update(range_name="A1", values=[headers])
    col = {h: i for i, h in enumerate(headers)}

    def cell(r: list, h: str) -> str:
        i = col[h]
        return str(r[i]).strip() if i < len(r) else ""

    in_sheet = {}
    for n, r in enumerate(values[1:], start=2):
        if cell(r, "Outreach ID").isdigit():
            in_sheet[int(cell(r, "Outreach ID"))] = (n, r)

    conn = get_conn()
    client_id = get_client_id(conn, client)
    # 1. Pull your edits and approvals (only while the email hasn't gone out)
    for oid, (_, r) in in_sheet.items():
        row = conn.execute("SELECT * FROM outreach WHERE id = ? AND client_id = ?", (oid, client_id)).fetchone()
        if row and settings["mode"] == "manual":
            _pull_manual(conn, client_id, row, lambda h: cell(r, h) if h in col else "")
            row = conn.execute("SELECT * FROM outreach WHERE id = ?", (oid,)).fetchone()
        if not row or row["status"] not in ("drafted", "approved"):
            continue
        approved = cell(r, "Approve").upper() in ("TRUE", "YES", "1", "X")
        status = "approved" if approved else "drafted"
        conn.execute("UPDATE outreach SET subject = ?, body = ?, follow_up_body = ?, approved = ?, status = ?, "
                     "approved_at = CASE WHEN ? AND approved_at IS NULL THEN ? ELSE approved_at END, "
                     "updated_at = ? WHERE id = ?",
                     (cell(r, "Subject") or row["subject"], cell(r, "Email") or row["body"],
                      cell(r, "Follow-up"), int(approved), status, int(approved), _now().isoformat(),
                      _now().isoformat(), oid))
        _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (oid,)).fetchone())
    conn.commit()

    rows = conn.execute("SELECT * FROM outreach WHERE client_id = ? ORDER BY id DESC", (client_id,)).fetchall()
    # 2. Push engine columns that changed
    updates = []
    for row in rows:
        if row["id"] not in in_sheet:
            continue
        n, r = in_sheet[row["id"]]
        for h in TAB_ENGINE:
            v = _cell_value(h, row)
            if cell(r, h) != v:
                updates.append({"range": rowcol_to_a1(n, col[h] + 1), "values": [[v]]})
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    # 3. New drafts at row 2, newest first
    new_rows = []
    for row in rows:
        if row["id"] in in_sheet:
            continue
        line = [""] * len(headers)
        for h in list(TAB_ENGINE) + list(TAB_EDITABLE):
            line[col[h]] = _cell_value(h, row)
        line[col["Approve"]] = False
        new_rows.append(line)
    if new_rows:
        ws.insert_rows(new_rows, row=2, value_input_option="RAW")
    conn.close()
    print(f"[{client}] outreach tab: {len(updates)} cells updated, {len(new_rows)} new drafts")
#--------------------------------------------------------------#

# Manual mode: your "Sent by me" ticks and Reply labels from the Outreach tab
def _pull_manual(conn, client_id: int, row, cell) -> None:
    ticked = lambda h: cell(h).upper() in ("TRUE", "YES", "1", "X")
    now = _now().isoformat()
    if ticked("Sent by me") and not row["sent_at"] and row["status"] in ("approved", "alerted"):
        conn.execute("UPDATE outreach SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, row["id"]))
    if ticked("Follow-up sent by me") and not row["follow_up_sent_at"] and row["status"] in ("sent", "follow_up_alerted"):
        conn.execute("UPDATE outreach SET status = 'followed_up', follow_up_sent_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, row["id"]))
    label = cell("Reply label").strip().lower().replace(" ", "_")
    if label in REPLY_LABELS and label != (row["reply_label"] or ""):
        status = "replied" if label != "out_of_office" else row["status"]
        conn.execute("UPDATE outreach SET reply_label = ?, status = ?, replied_at = COALESCE(replied_at, ?), "
                     "updated_at = ? WHERE id = ?", (label, status, now, now, row["id"]))
        if label in ("unsubscribe", "not_interested"):
            _block(conn, client_id, row["to_email"], label)
    _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (row["id"],)).fetchone())
#--------------------------------------------------------------#

# Read replies and bounces; a reply stops the follow-up
def check_replies(client: str, conn, client_id: int) -> int:
    rows = conn.execute("SELECT * FROM outreach WHERE client_id = ? AND sent_at IS NOT NULL",
                        (client_id,)).fetchall()
    if not rows:
        return 0
    by_id = {}
    for row in rows:
        for mid in (row["message_id"], row["follow_up_message_id"]):
            if mid:
                by_id[mid.strip()] = row
    by_email = {row["to_email"]: row for row in rows}
    found = 0
    for m in outreach_mail.recent_messages(client):
        if m["message_id"] in by_id:                  # our own email (e.g. a test sent to yourself)
            continue
        if not m["message_id"] or conn.execute("SELECT 1 FROM outreach_replies WHERE message_id = ?",
                                               (m["message_id"],)).fetchone():
            continue
        # Bounce: the delivery report names the address it couldn't deliver to
        if m["from"].startswith(("mailer-daemon", "postmaster")):
            row = next((r for e, r in by_email.items() if e in m["text"].lower()), None)
            if row:
                conn.execute("UPDATE outreach SET status = 'bounced', updated_at = ? WHERE id = ?",
                             (_now().isoformat(), row["id"]))
                _block(conn, client_id, row["to_email"], "bounced")
                conn.execute("INSERT INTO outreach_replies (client_id, outreach_id, from_email, subject, body, "
                             "label, message_id, received_at, created_at) VALUES (?, ?, ?, ?, ?, 'bounced', ?, ?, ?)",
                             (client_id, row["id"], m["from"], m["subject"], m["text"][:2000], m["message_id"],
                              m["received_at"], _now().isoformat()))
                _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (row["id"],)).fetchone())
                conn.commit()
                print(f"  bounced: {row['to_email']}")
            continue
        row = next((r for mid, r in by_id.items() if mid in m["in_reply_to"]), None) or by_email.get(m["from"])
        if not row:
            continue
        label = call_llm("outreach_reply_label", LABEL_PROMPT.format(text=m["text"][:3000] or m["subject"]),
                         ReplyLabel, client_id, max_tokens=200)
        conn.execute("INSERT INTO outreach_replies (client_id, outreach_id, from_email, subject, body, label, "
                     "summary, message_id, received_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (client_id, row["id"], m["from"], m["subject"], m["text"][:4000], label.label,
                      label.summary, m["message_id"], m["received_at"], _now().isoformat()))
        if label.label != "out_of_office":            # an absence reply doesn't stop the follow-up
            conn.execute("UPDATE outreach SET status = 'replied', replied_at = ?, reply_label = ?, "
                         "reply_text = ?, updated_at = ? WHERE id = ?",
                         (m["received_at"], label.label, label.summary, _now().isoformat(), row["id"]))
        if label.label in ("unsubscribe", "not_interested"):
            _block(conn, client_id, row["to_email"], label.label)
        _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (row["id"],)).fetchone())
        conn.commit()
        found += 1
        print(f"  reply from {m['from']}: {label.label} ({label.summary})")
    return found
#--------------------------------------------------------------#

# Send at most one email: a due follow-up first, then the oldest approved first email
def send_next(client: str, cfg, settings: dict, conn, client_id: int) -> str:
    now = _now()
    sender_tz = ZoneInfo(settings["sender_timezone"])
    today = now.astimezone(sender_tz).date().isoformat()
    sends = []
    for r in conn.execute("SELECT sent_at, follow_up_sent_at FROM outreach WHERE client_id = ?", (client_id,)):
        sends += [t for t in (r["sent_at"], r["follow_up_sent_at"]) if t]
    sent_today = sum(1 for t in sends if datetime.fromisoformat(t).astimezone(sender_tz).date().isoformat() == today)
    if sent_today >= settings["daily_limit"]:
        return f"daily limit reached ({sent_today}/{settings['daily_limit']})"
    if sends:
        last = max(datetime.fromisoformat(t) for t in sends)
        gap = timedelta(minutes=settings["min_gap_minutes"] + random.randint(0, 30))
        if now - last < gap:
            return "waiting: too soon after the last send"

    signature = settings.get("signature", "").strip()
    footer = f"\n\n{signature}\n\n{settings['opt_out_line']}" if signature else f"\n\n{settings['opt_out_line']}"
    sender = settings.get("sender_name", cfg.display_name)

    # 1. Follow-ups that are due
    for row in conn.execute("SELECT * FROM outreach WHERE client_id = ? AND status = 'sent' AND "
                            "COALESCE(follow_up_body, '') != '' ORDER BY sent_at", (client_id,)).fetchall():
        if _working_days_since(row["sent_at"], row["timezone"], now) < settings["follow_up_after_days"] \
                or not _in_window(row["timezone"], settings, now) or _blocked(conn, row["to_email"]):
            continue
        try:
            mid = outreach_mail.send(client, sender, row["to_email"], f"Re: {row['subject']}",
                                     row["follow_up_body"].strip() + footer, reply_to_id=row["message_id"])
        except Exception as e:
            conn.execute("UPDATE outreach SET error = ?, updated_at = ? WHERE id = ?",
                         (str(e)[:300], now.isoformat(), row["id"]))
            conn.commit()
            return f"follow-up failed for {row['to_email']}: {e}"
        conn.execute("UPDATE outreach SET status = 'followed_up', follow_up_sent_at = ?, follow_up_message_id = ?, "
                     "updated_at = ? WHERE id = ?", (now.isoformat(), mid, now.isoformat(), row["id"]))
        _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (row["id"],)).fetchone())
        conn.commit()
        return f"follow-up sent to {row['to_email']} ({row['company']})"

    # 2. Approved first emails
    for row in conn.execute("SELECT * FROM outreach WHERE client_id = ? AND status = 'approved' "
                            "ORDER BY approved_at", (client_id,)).fetchall():
        if _blocked(conn, row["to_email"]):
            conn.execute("UPDATE outreach SET status = 'skipped', updated_at = ? WHERE id = ?",
                         (now.isoformat(), row["id"]))
            conn.commit()
            continue
        if not _in_window(row["timezone"], settings, now):
            continue
        try:
            mid = outreach_mail.send(client, sender, row["to_email"], row["subject"], row["body"].strip() + footer)
        except Exception as e:                        # login or network problem: keep it queued, report it
            conn.execute("UPDATE outreach SET error = ?, updated_at = ? WHERE id = ?",
                         (str(e)[:300], now.isoformat(), row["id"]))
            conn.commit()
            return f"send failed for {row['to_email']}: {e}"
        conn.execute("UPDATE outreach SET status = 'sent', sent_at = ?, message_id = ?, error = NULL, updated_at = ? "
                     "WHERE id = ?", (now.isoformat(), mid, now.isoformat(), row["id"]))
        _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (row["id"],)).fetchone())
        conn.commit()
        return f"sent to {row['to_email']} ({row['company']})"
    return "nothing due in a recipient's working hours"
#--------------------------------------------------------------#

# Manual mode: the alert email (one block per draft, ready to copy or open in Outlook)
def _alert_html(cfg, settings: dict, items: list[tuple[str, object]], footer: str, conn) -> str:
    esc = lambda t: (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    blocks = []
    for n, (step, row) in enumerate(items, start=1):
        lead = conn.execute("SELECT contact_title, contact_linkedin FROM leads WHERE id = ?", (row["lead_id"],)).fetchone()
        follow = step == "follow_up"
        subject = f"Re: {row['subject']}" if follow else row["subject"]
        body = (row["follow_up_body"] if follow else row["body"]).strip() + footer
        mailto = f"mailto:{row['to_email']}?subject={quote(subject)}&body={quote(body)}"
        who = " · ".join(x for x in (row["to_name"], lead and lead["contact_title"]) if x)
        linkedin = f' · <a href="{lead["contact_linkedin"]}">LinkedIn</a>' if lead and lead["contact_linkedin"] else ""
        why = esc(row["signal"]) + (f' (<a href="{row["link"]}">source</a>)' if row["link"] else "")
        note = (f"<p style='color:#a15c00'>Follow-up: send it as a <b>reply</b> to your first email "
                f"(search your Sent folder for \"{esc(row['subject'])}\").</p>") if follow else ""
        blocks.append(f"""
<div style="border:1px solid #ddd;border-radius:8px;padding:14px 16px;margin:0 0 18px">
  <div style="font-size:15px"><b>{n}. {esc(row['company'])}</b>{' — follow-up' if follow else ''}</div>
  <div style="color:#555;margin:4px 0 10px">{esc(who)}{linkedin}<br>Why now: {why}</div>
  {note}
  <div><b>To:</b> {esc(row['to_email'])}</div>
  <div style="margin:6px 0"><b>Subject:</b> {esc(subject)}</div>
  <pre style="white-space:pre-wrap;font-family:inherit;background:#f7f7f7;padding:10px;border-radius:6px">{esc(body)}</pre>
  <a href="{mailto}" style="display:inline-block;padding:8px 14px;background:#0f6cbd;color:#fff;border-radius:6px;text-decoration:none">Open in Outlook</a>
</div>""")
    sheet = f"https://docs.google.com/spreadsheets/d/{cfg.sheets['spreadsheet_id']}"
    return (f"<div style='font-family:Arial,sans-serif;max-width:680px'>{''.join(blocks)}"
            f"<p>After sending, tick <b>Sent by me</b> (or <b>Follow-up sent by me</b>) in the "
            f"<a href='{sheet}'>Outreach tab</a>. Got a reply? Pick a <b>Reply label</b> there.</p></div>")

def run_alerts(client: str, cfg, settings: dict, conn, client_id: int, test: bool = False) -> str:
    now = _now()
    local = now.astimezone(ZoneInfo(settings["alert_timezone"]))
    slots = [h for h in settings["alert_hours"] if h <= local.hour]
    if not test:
        if local.weekday() >= 5 or not slots:
            return "no alert due (outside alert hours)"
        slot = f"{local.date().isoformat()} {max(slots):02d}:00"
        if local.hour >= max(slots) + settings["alert_grace_hours"]:
            return "no alert due (missed slot)"
        if conn.execute("SELECT 1 FROM outreach_alerts WHERE client_id = ? AND slot = ?", (client_id, slot)).fetchone():
            return f"alert for {slot} already sent"

    items = []
    for row in conn.execute("SELECT * FROM outreach WHERE client_id = ? AND status = 'sent' AND follow_up_alerted_at IS NULL "
                            "AND COALESCE(follow_up_body, '') != '' ORDER BY sent_at", (client_id,)).fetchall():
        if _working_days_since(row["sent_at"], row["timezone"], now) >= settings["follow_up_after_days"] \
                and not _blocked(conn, row["to_email"]):
            items.append(("follow_up", row))
    for row in conn.execute("SELECT * FROM outreach WHERE client_id = ? AND status = 'approved' AND alerted_at IS NULL "
                            "ORDER BY approved_at", (client_id,)).fetchall():
        if not _blocked(conn, row["to_email"]):
            items.append(("first", row))
    items = items[: settings["per_alert"]]
    if not items:
        return "no alert: nothing approved and waiting"

    signature = settings.get("signature", "").strip()
    footer = f"\n\n{signature}\n\n{settings['opt_out_line']}" if signature else f"\n\n{settings['opt_out_line']}"
    html = _alert_html(cfg, settings, items, footer, conn)
    title = f"{'[TEST] ' if test else ''}{cfg.display_name}: {len(items)} email{'s' if len(items) > 1 else ''} to send — " \
            + ", ".join(r["company"] for _, r in items)
    send_email(title, html, settings["alert_to"])
    if test:
        return f"test alert sent to {', '.join(settings['alert_to'])}"

    stamp = now.isoformat()
    for step, row in items:
        if step == "first":
            conn.execute("UPDATE outreach SET status = 'alerted', alerted_at = ?, updated_at = ? WHERE id = ?",
                         (stamp, stamp, row["id"]))
        else:
            conn.execute("UPDATE outreach SET status = 'follow_up_alerted', follow_up_alerted_at = ?, updated_at = ? "
                         "WHERE id = ?", (stamp, stamp, row["id"]))
        _refresh_lead(conn, conn.execute("SELECT * FROM outreach WHERE id = ?", (row["id"],)).fetchone())
    conn.execute("INSERT INTO outreach_alerts (client_id, slot, items, sent_at) VALUES (?, ?, ?, ?)",
                 (client_id, slot, ",".join(str(r["id"]) for _, r in items), stamp))
    conn.commit()
    return f"alert sent for {slot}: " + ", ".join(f"{r['company']} ({s})" for s, r in items)
#--------------------------------------------------------------#

# Every 30 minutes (cron): replies, approvals, one send, sheet update
def run_outreach(client: str) -> None:
    cfg = load_config(client)
    settings = _settings(cfg)
    sync_tab(client)                                 # your approvals, edits and ticks first
    conn = get_conn()
    client_id = get_client_id(conn, client)
    if settings["mode"] == "manual":                 # alerts only: you send from your own mailbox
        result = run_alerts(client, cfg, settings, conn, client_id)
        conn.close()
        print(f"[{client}] outreach (manual) {datetime.now():%Y-%m-%d %H:%M}: {result}")
        if result.startswith("alert sent"):
            sync_tab(client)
            sync(client)
        return
    replies = check_replies(client, conn, client_id)
    result = send_next(client, cfg, settings, conn, client_id)
    stats = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM outreach WHERE client_id = ? GROUP BY status", (client_id,))}
    conn.close()
    print(f"[{client}] outreach {datetime.now():%Y-%m-%d %H:%M}: {result}; {replies} new replies; "
          + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    if replies or not result.startswith(("daily limit", "waiting", "nothing")):
        sync_tab(client)
        sync(client)
#--------------------------------------------------------------#

# Test: send the newest draft to yourself (nothing is marked as sent) and check the inbox login
def send_test(client: str, to: str) -> None:
    cfg = load_config(client)
    settings = _settings(cfg)
    conn = get_conn()
    client_id = get_client_id(conn, client)
    if settings["mode"] == "manual":                 # manual mode: preview an alert, nothing is marked
        print(f"[{client}] {run_alerts(client, cfg, settings, conn, client_id, test=True)}")
        conn.close()
        return
    row = conn.execute("SELECT * FROM outreach WHERE client_id = ? ORDER BY id DESC LIMIT 1", (client_id,)).fetchone()
    conn.close()
    subject = f"[TEST] {row['subject']}" if row else "[TEST] outreach setup"
    body = row["body"] if row else "If you can read this, sending works."
    signature = settings.get("signature", "").strip()
    outreach_mail.send(client, settings.get("sender_name", cfg.display_name), to, subject,
                       body.strip() + f"\n\n{signature}\n\n{settings['opt_out_line']}")
    print(f"[{client}] test email sent to {to}")
    print(f"[{client}] inbox check: {len(outreach_mail.recent_messages(client, days=1))} messages in the last day")
#--------------------------------------------------------------#

# Which templates work: per type, how many were sent, replied, and were interested
def report(client: str) -> None:
    conn = get_conn()
    client_id = get_client_id(conn, client)
    print(f"[{client}] outreach results (type: sent / replied / interested or question / edited before sending)")
    for r in conn.execute(
            """SELECT kind, COUNT(*) AS sent,
                      TOTAL(status = 'replied') AS replied,
                      TOTAL(reply_label IN ('interested', 'question')) AS positive,
                      TOTAL(body != draft_body OR subject != draft_subject) AS edited
               FROM outreach WHERE client_id = ? AND sent_at IS NOT NULL GROUP BY kind""", (client_id,)):
        print(f"  {r['kind']:<8} {r['sent']} / {int(r['replied'])} / {int(r['positive'])} / {int(r['edited'])}")
    conn.close()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
