#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/views/dashboard.py
# Purpose: last runs, what's waiting for the team, and leads by stage
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import console_data as data
from views._ui import market_filter, in_market, go
#--------------------------------------------------------------#

st.title("Dashboard")
market = market_filter("dash_market")
leads = [l for l in data.leads() if in_market(l, market)]
runs = data.last_runs()
posts = data.engage_posts()
#--------------------------------------------------------------#

st.subheader("Last run")
c1, c2, c3, c4 = st.columns(4)
with c1, st.container(border=True):
    st.metric("Job search", data.ago(runs["job_search"]))
    st.caption(f"{runs['new_postings_7d']} new job posts in the last 7 days")
with c2, st.container(border=True):
    st.metric("Enrichment", data.ago(runs["enrichment"]))
    st.caption(f"{runs['enrich_waiting']} leads still being looked up")
with c3, st.container(border=True):
    st.metric("Posts to engage", data.ago(runs["posts"]))
    st.caption(f"{len([p for p in posts if not p['action']])} posts waiting")
with c4, st.container(border=True):
    st.metric("People search", data.ago(runs["people"]))
    st.caption("LinkedIn people to connect with")
#--------------------------------------------------------------#

st.subheader("Pending tasks")
reach = [l for l in leads if l["stage"] == "Enrichment"]
needs_contact = [l for l in leads if l["stage"] == "Raw leads" and not l["contact_name"]]
due = [l for l in leads if l["follow_up_due"]]
replies = [l for l in leads if l["stage"] == "Replied"]
todo_posts = [p for p in posts if not p["action"]]
tasks = [("Leads to reach out to", len(reach), "Email found, nothing sent yet", "leads", {"stage_filter": "Enrichment"}),
         ("Follow-ups due", len(due), "Follow-up 1, follow-up 2 or a check-in", "leads", {"stage_filter": "Follow-up"}),
         ("Replies", len(replies), "They wrote back", "leads", {"stage_filter": "Replied"}),
         ("Leads that need a contact", len(needs_contact), "Add a name from LinkedIn", "leads", {"stage_filter": "Raw leads"}),
         ("Posts to engage with", len(todo_posts), "Comment or reply this week", "engage", {})]
cols = st.columns(5)
for col, (label, n, note, page, state) in zip(cols, tasks):
    with col, st.container(border=True):
        st.metric(label, n)
        st.caption(note)
        if st.button("Open", key=f"task_{label}", width="stretch"):
            go(page, **state)
#--------------------------------------------------------------#

left, right = st.columns([3, 2])
with left:
    st.subheader("Leads by stage")
    counts = pd.DataFrame({"Stage": data.STAGES, "Leads": [sum(l["stage"] == s for l in leads) for s in data.STAGES]})
    st.bar_chart(counts, x="Stage", y="Leads", horizontal=True, color="#0b5d63", height=260)
with right:
    st.subheader("This month")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    new = [l for l in leads if (l["created_at"] or "").startswith(month)]
    emails = [l for l in leads if l["contact_email"] and (l["enriched_at"] or l["contact_checked_at"] or "").startswith(month)]
    sent = [l for l in leads if (l["sent_at"] or "").startswith(month)]
    spend = sum(e["inr"] for e in data.cost_events() if (e["at"] or "").startswith(month))
    with st.container(border=True):
        a, b = st.columns(2)
        a.metric("New leads", len(new))
        b.metric("Emails found", len(emails))
        a.metric("Emails sent", len(sent))
        b.metric("Spent", f"₹{spend:,.0f}")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
