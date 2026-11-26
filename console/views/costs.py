#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/views/costs.py
# Purpose: what the engine spent (AI, searches, email checks), cost per lead, and credits left.
#          All in INR. Exchange rates and the AI price come from .env, credits from config/console.yaml.
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import console_data as data
#--------------------------------------------------------------#

st.title("Costs")
st.caption("Everything the engine has spent on searches, AI and email checks, in rupees.")
events = data.cost_events()
leads = data.leads()
total = sum(e["inr"] for e in events)
month = datetime.now(timezone.utc).strftime("%Y-%m")
this_month = sum(e["inr"] for e in events if (e["at"] or "").startswith(month))
first = min((e["at"] for e in events if e["at"]), default=None)
per = data.cost_per_lead(leads, events)

k = st.columns(5)
k[0].metric("Spent so far", f"₹{total:,.0f}", help=f"Since {str(first)[:10] if first else '-'}")
k[1].metric("This month", f"₹{this_month:,.0f}")
k[2].metric("Average per lead", f"₹{per['avg']:,.1f}", help=f"{len(leads)} leads")
k[3].metric("Most for one lead", f"₹{per['max']:,.1f}", help=f"Estimate: {per['max_lead']}")
k[4].metric("Least for one lead", f"₹{per['min']:,.1f}", help=f"Estimate: {per['min_lead']}")
st.caption("Average = all lead spend ÷ leads. Most and least are estimates: job posts behind the lead × cost to "
           "classify one, plus a share of the enrichment cost.")

left, right = st.columns([3, 2])
with left:
    st.subheader("Spend by month")
    df = pd.DataFrame([{"Month": (e["at"] or "")[:7], "What": e["what"], "INR": e["inr"]} for e in events if e["at"]])
    if not df.empty:
        pivot = df.pivot_table(index="Month", columns="What", values="INR", aggfunc="sum").fillna(0)
        st.bar_chart(pivot, height=280)
        st.subheader("Where it goes")
        split = df.groupby("What")["INR"].sum().sort_values(ascending=False)
        st.dataframe(pd.DataFrame({"What": split.index, "Spent (INR)": split.round(0).values}),
                     hide_index=True, width="stretch")
with right:
    st.subheader("Credits left")
    for c in data.credits_left():
        with st.container(border=True):
            money = "INR" in c["label"] or "USD" in c["label"]
            fmt = (lambda v: f"{v:,.2f}") if money else (lambda v: f"{v:,.0f}")
            st.markdown(f"**{c['label']}**: {fmt(c['left'])} of {fmt(c['total'])}")
            st.progress(min(1.0, c["share"]))
            st.caption(("Resets on the 1st. " if c["resets"] else "") + f"Counted since {c['since'][:10]}.")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
