#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
from datetime import date, datetime, timezone
from html import escape

from job_alerts.core.config import load_config
from job_alerts.core.db import ROOT, get_conn, get_client_id
from job_alerts.core.email import send_email
#--------------------------------------------------------------#

def _entry(r) -> str:
    line = " · ".join(filter(None, [r["title"], r["company_name"], r["location"]]))
    return (
        f"<p><b>{escape(r['full_name'] or '')}</b><br>"
        f"{escape(line)}<br>"
        f"<span style='color:#555'>{escape(r['reason'] or '')}</span><br>"
        f"<a href=\"{escape(r['linkedin_url'])}\">LinkedIn profile</a></p>"
    )
#--------------------------------------------------------------#

def _section(title: str, rows) -> str:
    if not rows:
        return ""
    return f"<h3>{escape(title)} ({len(rows)})</h3>" + "".join(_entry(r) for r in rows)
#--------------------------------------------------------------#

def send_people_digest(client: str, dry_run: bool = False) -> None:
    cfg = load_config(client)
    limit = cfg.people_finder.get("weekly_target", 75)

    conn = get_conn()
    client_id = get_client_id(conn, client)
    rows = conn.execute(
        "SELECT * FROM people WHERE client_id = ? AND status = 'new' "
        "ORDER BY priority, created_at DESC LIMIT ?",
        (client_id, limit),
    ).fetchall()

    if not rows:
        print(f"[{client}] no new people to send")
        conn.close()
        return

    hiring = [r for r in rows if r["priority"] == 1]
    others = [r for r in rows if r["priority"] != 1]
    html = (
        f"<h2>{escape(cfg.display_name)}: people to connect with, week of {date.today():%d %b %Y}</h2>"
        f"<p>{len(rows)} people. Check each profile before connecting, and write each note yourself.</p>"
        + _section("At companies hiring for this now", hiring)
        + _section("Matching your target roles", others)
    )

    out = ROOT / "outputs" / client / "people" / f"{date.today()}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)

    if dry_run:
        print(f"[{client}] dry run: {len(rows)} people, saved to {out}")
        conn.close()
        return

    send_email(
        f"{cfg.display_name}: {len(rows)} people to connect with ({date.today():%d %b})",
        html, cfg.digest.email_to,
    )
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE people SET status = 'sent', sent_at = ? WHERE id = ?",
        [(now, r["id"]) for r in rows],
    )
    conn.commit()
    conn.close()
    print(f"[{client}] sent {len(rows)} people")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#