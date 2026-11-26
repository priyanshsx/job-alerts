#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/views/people.py
# Purpose: people worth connecting with on LinkedIn (found by people-find and the contacts command).
#          The team connects by hand; nothing here sends anything.
#--------------------------------------------------------------#

# Imports libraries
import pandas as pd
import streamlit as st
import console_data as data
#--------------------------------------------------------------#

st.title("People")
st.caption("People at hiring companies who are worth a LinkedIn connection. You connect by hand.")
people = data.people()
statuses = sorted({p["connection_status"] or "to connect" for p in people})
c1, c2 = st.columns([3, 2])
search = c1.text_input("Search", placeholder="Name, title or company", label_visibility="collapsed")
status = c2.selectbox("Status", ["All"] + statuses, label_visibility="collapsed")
if search:
    s = search.lower()
    people = [p for p in people if s in " ".join(str(p[k] or "") for k in ("full_name", "title", "company_name")).lower()]
if status != "All":
    people = [p for p in people if (p["connection_status"] or "to connect") == status]

df = pd.DataFrame([{
    "id": p["id"], "Name": p["full_name"], "Title": p["title"], "Company": p["company_name"],
    "Location": p["location"], "LinkedIn": p["linkedin_url"], "Why connect": p["reason"],
    "Status": p["connection_status"] or "to connect", "Email": p["email"], "Email status": p["email_status"],
    "Found on": (p["created_at"] or "")[:10], "Note": p["note"],
} for p in people])
if df.empty:
    st.info("No people match.")
    st.stop()
event = st.dataframe(df.drop(columns=["id"]), hide_index=True, width="stretch", height=560,
                     on_select="rerun", selection_mode="single-row",
                     column_config={"LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Open"),
                                    "Why connect": st.column_config.TextColumn(width="large")})
rows = event.selection.rows if event else []
if rows:
    person_id = int(df.iloc[rows[0]]["id"])
    sheet = data.sheet_cells("Person ID", person_id)
    with st.container(border=True):
        st.markdown(f"#### {df.iloc[rows[0]]['Name']}")
        st.write(df.iloc[rows[0]]["Why connect"] or "")
        for tab, cells in sheet.items():
            st.markdown(f"**From the sheet: {tab}**")
            st.dataframe(pd.DataFrame({"Column": list(cells), "Value": list(cells.values())}),
                         hide_index=True, width="stretch")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
