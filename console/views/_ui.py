#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/views/_ui.py
# Purpose: small pieces several pages share (market filter, stage tags)
#--------------------------------------------------------------#

# Imports libraries
import streamlit as st
import console_data as data
#--------------------------------------------------------------#

def market_filter(key: str) -> str:
    """Market chips; the choice is kept across pages."""
    options = ["All markets"] + data.markets()
    current = st.session_state.get("market", "All markets")
    choice = st.pills("Market", options, default=current if current in options else "All markets",
                      key=key, label_visibility="collapsed")
    st.session_state["market"] = choice or "All markets"
    return st.session_state["market"]

def in_market(lead: dict, market: str) -> bool:
    return market == "All markets" or lead["market"] == market

def email_tag(status: str | None) -> str:
    s = (status or "").lower()
    if s == "verified":
        return '<span class="tag">verified</span>'
    if s.startswith("risky") or "catch" in s:
        return '<span class="tag warn">risky</span>'
    return f'<span class="tag grey">{status or "not checked"}</span>'

def go(page: str, **state) -> None:
    """Open another page with some state set (e.g. a stage filter on Leads)."""
    st.session_state.update(state)
    st.switch_page(st.session_state["_pages"][page])
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
