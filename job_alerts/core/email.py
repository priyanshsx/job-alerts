#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from job_alerts.core.db import ROOT
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
#--------------------------------------------------------------#

def send_email(subject: str, html: str, to: list[str]) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = ", ".join(to)
    msg.set_content("This email is HTML; open it in an email client that shows HTML.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 465))) as smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#