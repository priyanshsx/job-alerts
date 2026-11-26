#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/app.py
# Purpose: the internal console. Reads the same database the terminal commands write.
# Run:     streamlit run console/app.py
#          (first: pip install -e ".[console]", the 017 migration, and scripts/import_sheet.py)
#--------------------------------------------------------------#

# Imports libraries
import sys
from pathlib import Path
import streamlit as st
sys.path.insert(0, str(Path(__file__).resolve().parent))          # console_data, views
sys.path.insert(1, str(Path(__file__).resolve().parent.parent))   # job_alerts, even if not pip-installed
import console_data as data
#--------------------------------------------------------------#

st.set_page_config(page_title=f"{data.cfg()['brand']} GTM", page_icon="◆", layout="wide")
st.markdown("""<style>
[data-testid="stMetricValue"]{font-size:1.7rem}
div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff}
[data-testid="stSidebar"] h3{color:#fff}
[data-testid="stMetricLabel"]{color:#5d6470}
.small{font-size:0.82rem;color:#5d6470}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:0.75rem;background:#e7f1f1;color:#0b5d63;margin-right:4px}
.tag.warn{background:#fdf1e3;color:#92400e}.tag.grey{background:#eef0f3;color:#454b55}
</style>""", unsafe_allow_html=True)

leads = data.leads()
open_leads = [l for l in leads if l["stage"] != "Not a fit"]
people_count = len(data.people())
engage_todo = len([p for p in data.engage_posts() if not p["action"]])

pages = [
    st.Page("views/dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True),
    st.Page("views/leads.py", title=f"Leads ({len(open_leads)})", icon=":material/work:", url_path="leads"),
    st.Page("views/people.py", title=f"People ({people_count})", icon=":material/group:", url_path="people"),
    st.Page("views/engage.py", title=f"Engage ({engage_todo})", icon=":material/forum:", url_path="engage"),
    st.Page("views/costs.py", title="Costs", icon=":material/payments:", url_path="costs"),
]
st.sidebar.markdown(f"### {data.cfg()['brand']} GTM")
nav = st.navigation(pages)
st.session_state["_pages"] = {p.url_path or "dashboard": p for p in pages}
nav.run()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
