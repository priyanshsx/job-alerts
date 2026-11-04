#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports Libraries
import re
import unicodedata
#--------------------------------------------------------------#

# Global variables 
LEGAL_FORMS = r"\b(gmbh|mbh|ag|kg|kgaa|se|ug|co|ltd|limited|inc|llc|plc|bv|nv|sarl|sas|spa|srl|oy|ab|holding|group|gruppe)\b"
#--------------------------------------------------------------#

def normalize_name(name: str | None) -> str:
    s = (name or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[&.,()\-/+]", " ", s)
    s = re.sub(LEGAL_FORMS, " ", s)
    return re.sub(r"\s+", " ", s).strip()
#--------------------------------------------------------------#
#----------------------End-of-code-----------------------------#