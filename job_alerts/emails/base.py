#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/emails/base.py
# Purpose: the shared result shape for every email provider, and small helpers.
#--------------------------------------------------------------#

# Imports libraries
import re
from dataclasses import dataclass
#--------------------------------------------------------------#

# What every provider returns
@dataclass
class EmailResult:
    email: str | None          # None = not found
    status: str                # verified, risky, not_found, error
    credits: int = 0           # credits this lookup used (0 when nothing was found, for most providers)
    detail: str = ""           # provider's own status or error message, for the log
#--------------------------------------------------------------#

# Raised when a provider can't be used at all (no key, no API access on this plan)
class ProviderUnavailable(Exception):
    pass
#--------------------------------------------------------------#

# Split "Dr. Anna-Lena Müller" into ("Anna-Lena", "Müller")
TITLES = re.compile(r"^(dr|prof|mr|mrs|ms|dipl|ing|mag)\.?$", re.IGNORECASE)

def split_name(full_name: str | None) -> tuple[str, str]:
    parts = [p for p in (full_name or "").replace(",", " ").split() if not TITLES.match(p.strip("."))]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
