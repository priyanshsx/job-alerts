#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries 
import os 
import smtplib
from datetime import date, datetime, timezone
from email.message import EmailMessage
from html import escape
from urllib.parse import quote_plus
from dotenv import load_dotenv
from job_alerts.core.config import load_config
from job_alerts.core.db import ROOT, get_conn, get_client_id
#--------------------------------------------------------------#

load_dotenv(ROOT / ".env")
#--------------------------------------------------------------#

EMPLOYER_LABELS = {
    "manufacturer_supplier": "Manufacturer / supplier",
    "consultancy": "Consultancy", 
    "other_industry": "Mid-sized company, other industry",
    "unknown": "Company not recognized",
    "large_enterprise": "Large enterrise"
}
#--------------------------------------------------------------#

def _search_link(text: str, query: str, url: str) -> str:
    return f'<a href="{url}{quote_plus(query)}">{escape(text)}</a>'

def _entry(r) -> str:
    company = r["company_name"] or "Unknown company"
    linkedin = "https://www.linkedin.com/search/results/people/?keywords="
    links = [
        f'<a href="{escape(r["url"])}">Job posting</a>',
        _search_link("LinkedIn: Head of IT", f"Head of IT {company}", linkedin),
        _search_link("LinkedIn: master data", f"master data {company}", linkedin),
        _search_link("Company", company, "https://www.google.com/search?q=")
    ]
    erp = r["erp_system"] if r["erp_system"] not in (None, "unknown", "other") else None
    details = " · ".join(filter(None, [
        EMPLOYER_LABELS.get(r["employer_type"], r["employer_type"]),
        f"{r['role_type']} role",
        erp.upper() if erp else None,
    ]))
    return (
        f"<p><b>{escape(r['title'] or '')}</b><br>"
        f"{escape(company)} · {escape(r['location'] or '')} · posted {escape(r['posted_at'] or '')}<br>"
        f"<span style='color:#555'>{escape(details)}</span><br>"
        f"{' · '.join(links)}</p>"
    )
#--------------------------------------------------------------#

def _section(title: str, rows) -> str:
    if not rows:
        return ""
    return f"<h3>{escape(title)} ({len(rows)})</h3>" + "".join(_entry(r) for r in rows)
#--------------------------------------------------------------#

# Sends the mailer 
def send_digest(client: str, dry_run: bool = False) -> None:
    cfg = load_config(client)
    max_priority = cfg.job_alerts.get("digest_max_priority", 2)

    conn = get_conn()
    client_id = get_client_id(conn, client)
    unsent = "id NOT IN (SELECT job_posting_id FROM alerts_sent WHERE client_id = ?)"
    rows = conn.execute(
        f"SELECT * FROM job_postings WHERE client_id = ? AND is_relevant = 1 "
        f"AND priority <= ? AND {unsent} ORDER BY priority, posted_at DESC",
        (client_id, max_priority, client_id),
    ).fetchall()[: cfg.digest.max_items]

    if not rows:
        print(f"[{client}] nothing new to send")
        conn.close()
        return 

    targets = [r for r in rows if r["priority"] == 1]
    partners = [r for r in rows if r["priority"] > 1 and r["employer_type"] == "consultancy"]
    others = [r for r in rows if r["priority"] > 1 and r["employer_type"] != "consultancy"]

    html = (
        f"<h2>{escape(cfg.display_name)} job alerts, {date.today():%d %b %Y}</h2>"
        f"<p>{len(rows)} new postings. Links open LinkedIn searches; check each profile before reaching out.</p>"
        + _section("Target suppliers", targets)
        + _section("Worth a look", others)
        + _section("Partner leads: consultancies hiring", partners)
    )

    out = ROOT / "outputs" / client / "digests" / f"{date.today()}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)

    if dry_run: 
        print(f"[{client}] dry run: {len(rows)} postings, saved to {out}")
        conn.close()
        return 

    msg = EmailMessage()
    msg["Subject"] = f"{cfg.display_name} job alerts: {len(rows)} new ({date.today():%d %b})"
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["TO"] = ", ".join(cfg.digest.email_to)
    msg.set_content("This digest is HTML; open it in an email client that shows HTML.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 465))) as smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)

    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT INTO alerts_sent (client_id, job_posting_id, sent_at) VALUES (?, ?, ?) "
        "ON CONFLICT DO NOTHING",
        [(client_id, r["id"], now) for r in rows],
    )
    conn.commit()
    conn.close()
    print(f"[{client}] sent {len(rows)} postings to {msg['To']}")
#--------------------------------------------------------------#
#---------------------------end-of-code------------------------#