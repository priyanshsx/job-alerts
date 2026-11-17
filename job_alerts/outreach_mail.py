#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/outreach_mail.py
# Purpose: send and read outreach email through a normal mailbox (free, no sending tool).
#          Gmail / Google Workspace: SMTP to send, IMAP to read replies, logged in with an
#          app password. The address and app password come from .env, per client:
#            <CLIENT>_EMAIL_ADDRESS=you@gmail.com
#            <CLIENT>_EMAIL_APP_PASSWORD=abcdefghijklmnop
#--------------------------------------------------------------#

# Imports libraries
import imaplib
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr, parsedate_to_datetime
from dotenv import load_dotenv
from job_alerts.core.db import ROOT
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
IMAP_HOST = "imap.gmail.com"
#--------------------------------------------------------------#

# The mailbox login for one client
def credentials(client: str) -> tuple[str, str]:
    prefix = client.upper()
    address = os.getenv(f"{prefix}_EMAIL_ADDRESS")
    password = (os.getenv(f"{prefix}_EMAIL_APP_PASSWORD") or "").replace(" ", "")
    if not address or not password:
        raise RuntimeError(f"{prefix}_EMAIL_ADDRESS and {prefix}_EMAIL_APP_PASSWORD must be set in .env")
    return address, password
#--------------------------------------------------------------#

# Send one plain-text email; returns its Message-ID (used to match replies and thread follow-ups)
def send(client: str, sender_name: str, to: str, subject: str, body: str,
         reply_to_id: str | None = None) -> str:
    address, password = credentials(client)
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, address))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=address.split("@")[-1])
    if reply_to_id:                                   # follow-up: same thread as the first email
        msg["In-Reply-To"] = reply_to_id
        msg["References"] = reply_to_id
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)                        # Gmail keeps a copy in Sent
    return msg["Message-ID"]
#--------------------------------------------------------------#

# Plain text of an email (the reply itself, without the quoted earlier messages where possible)
def _text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    text = part.get_content() if part else ""
    if part is not None and part.get_content_type() == "text/html":
        import re
        text = re.sub(r"<[^>]+>", " ", text)
    lines = []
    for line in text.splitlines():
        if line.startswith(">") or (line.startswith("On ") and line.rstrip().endswith("wrote:")):
            break
        lines.append(line)
    return "\n".join(lines).strip()[:4000]
#--------------------------------------------------------------#

# Inbox messages from the last few days (read-only: nothing is marked as read)
def recent_messages(client: str, days: int = 7) -> list[dict]:
    address, password = credentials(client)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    out = []
    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(address, password)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, "SINCE", since)
        for num in (data[0] or b"").split():
            _, parts = imap.fetch(num, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if not raw:
                continue
            msg = message_from_bytes(raw, policy=policy.default)
            try:
                received = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                received = datetime.now(timezone.utc).isoformat()
            out.append({
                "message_id": (msg["Message-ID"] or "").strip(),
                "from": parseaddr(msg["From"] or "")[1].lower(),
                "subject": str(msg["Subject"] or ""),
                "in_reply_to": f"{msg['In-Reply-To'] or ''} {msg['References'] or ''}",
                "text": _text(msg),
                "received_at": received,
            })
    return out
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
