#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/views/leads.py
# Purpose: every lead from every market, as a board (five stages) or a table, plus one lead's page.
#          Cards move by themselves:
#            Raw leads -> Enrichment   when "Run enrichment" (or the scheduled crawler) finds an email
#            -> Sent / Follow-up       when the team logs the first email and the follow-ups (with dates)
#            -> Replied                when a reply is logged
#          Follow-ups: 7 days after the first email, 5 days after follow-up 1, then a check-in every
#          25 days (config/console.yaml, follow_ups).
#--------------------------------------------------------------#

# Imports libraries
from datetime import date
import pandas as pd
import streamlit as st
import console_data as data
from views._ui import market_filter, in_market, email_tag
#--------------------------------------------------------------#

# Global variables
CARDS_PER_COLUMN = 25
#--------------------------------------------------------------#

def open_lead(lead_id: int) -> None:
    st.query_params["lead"] = str(lead_id)

def close_lead() -> None:
    st.query_params.pop("lead", None)

def nice(day: str | None) -> str:
    """'2026-11-26' -> '26 Nov 2026'."""
    try:
        return date.fromisoformat(day[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return ""

def next_step_tag(lead: dict) -> str:
    if not lead["next_label"]:
        return ""
    if lead["follow_up_due"]:
        return f"<span class='tag warn'>{lead['next_label']} due</span>"
    return f"<span class='tag grey'>{lead['next_label']} on {nice(lead['next_due'])}</span>"
#--------------------------------------------------------------#

def card(lead: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{lead['company_name']}**  \n"
                    f"<span class='small'>{lead['market']} · {lead['country'] or '?'} · "
                    f"{data.ago(lead['signal_iso'])}</span>", unsafe_allow_html=True)
        st.markdown(f"<span class='small'>{(lead['latest_signal'] or '').removeprefix('Hiring: ')[:90]}</span>",
                    unsafe_allow_html=True)
        if lead["contact_email"]:
            who = lead["contact_name"] or lead["contact_email"].split("@")[0]
            st.markdown(f"<span class='small'>{who}</span> {email_tag(lead['email_status'])}", unsafe_allow_html=True)
        elif lead["contact_name"]:
            st.markdown(f"<span class='small'>{lead['contact_name']}</span> <span class='tag grey'>ready to enrich</span>",
                        unsafe_allow_html=True)
        elif lead["stage"] == "Raw leads":
            st.markdown("<span class='tag grey'>needs a contact</span>", unsafe_allow_html=True)
        if lead["stage"] in ("Sent", "Follow-up"):
            st.markdown(f"<span class='small'>{lead['emails_sent']} of 3 emails sent</span> {next_step_tag(lead)}",
                        unsafe_allow_html=True)
        st.button("Open", key=f"open_{lead['id']}", on_click=open_lead, args=(lead["id"],), width="stretch")

def column_order(stage: str, leads: list[dict]) -> list[dict]:
    if stage in ("Sent", "Follow-up"):                     # due first (oldest due on top), all-3-sent at the end
        return sorted(leads, key=lambda l: (l["order"], l["next_due"] or ""))
    return leads

def board(leads: list[dict]) -> None:
    cols = st.columns(len(data.STAGES))
    days = data.schedule()
    ready = [l["id"] for l in leads if l["stage"] == "Raw leads" and l["contact_name"]]
    for col, stage in zip(cols, data.STAGES):
        in_stage = column_order(stage, [l for l in leads if l["stage"] == stage])
        with col:
            st.markdown(f"**{stage}** · {len(in_stage)}")
            st.caption(data.STAGE_RULES[stage].format(**days))
            if stage == "Raw leads" and ready:
                if st.button(f"Enrich {len(ready)} with a contact", key="enrich_all", type="primary", width="stretch"):
                    run_enrichment(ready)
            limit = st.session_state.get(f"more_{stage}", CARDS_PER_COLUMN)
            for lead in in_stage[:limit]:
                card(lead)
            if len(in_stage) > limit:
                if st.button(f"Show {min(CARDS_PER_COLUMN, len(in_stage) - limit)} more", key=f"more_btn_{stage}"):
                    st.session_state[f"more_{stage}"] = limit + CARDS_PER_COLUMN
                    st.rerun()

def table(leads: list[dict]) -> None:
    df = pd.DataFrame([{
        "id": l["id"], "Company": l["company_name"], "Market": l["market"], "Country": l["country"],
        "Stage": l["stage"], "Signal": (l["latest_signal"] or "").removeprefix("Hiring: "),
        "Signal date": l["signal_iso"][:10], "Priority": l["priority"],
        "Contact": l["contact_name"], "Email": l["contact_email"], "Email status": l["email_status"],
        "First email": l["first_email_on"], "Emails sent": l["emails_sent"] or None,
        "Next": f"{l['next_label']} {'due' if l['follow_up_due'] else 'on'} {l['next_due']}" if l["next_label"] else None,
        "Domain": l["domain"], "Notes": l["notes"],
    } for l in leads])
    if df.empty:
        st.info("No leads match.")
        return
    event = st.dataframe(df.drop(columns=["id"]), hide_index=True, width="stretch", height=620,
                         on_select="rerun", selection_mode="single-row")
    rows = event.selection.rows if event else []
    if rows:
        open_lead(int(df.iloc[rows[0]]["id"]))
        st.rerun()
#--------------------------------------------------------------#

def run_enrichment(lead_ids: list[int]) -> None:
    bar = st.progress(0.0, text="Starting enrichment…")
    def progress(n, total, company):
        bar.progress((n - 1) / total, text=f"{n} of {total}: {company} (reading the website, checking emails)")
    lines = data.enrich_now(lead_ids, progress)
    bar.progress(1.0, text="Done")
    st.session_state["enrich_result"] = lines
    st.rerun()

def show_enrich_result() -> None:
    lines = st.session_state.pop("enrich_result", None)
    if lines:
        with st.container(border=True):
            st.markdown("**Enrichment finished**")
            for line in lines:
                st.caption(line)
#--------------------------------------------------------------#

def contact_box(lead: dict) -> None:
    with st.container(border=True):
        st.markdown("#### Contact")
        st.caption("Paste the person from LinkedIn, check the company name, then run enrichment to find their email.")
        with st.form(f"contact_{lead['id']}", border=False):
            name = st.text_input("Name", value=lead["contact_name"] or "")
            linkedin = st.text_input("LinkedIn profile", value=lead["contact_linkedin"] or "",
                                     placeholder="https://www.linkedin.com/in/…")
            company = st.text_input("Company name", value=lead["company_name"] or "",
                                    help="Filled in by the engine. Correct it if it's wrong.")
            c1, c2 = st.columns(2)
            title = c1.text_input("Title (optional)", value=lead["contact_title"] or "")
            domain = c2.text_input("Website (optional)", value=lead["domain"] or "",
                                   help="Only if the engine has the wrong website. Yours always wins.")
            if st.form_submit_button("Save contact", width="stretch"):
                result = data.save_contact(lead["id"], name, linkedin, company, title, domain)
                st.toast(f"Contact {result}")
                st.rerun()
        label = "Run enrichment again" if lead["contact_email"] else "Run enrichment"
        if st.button(label, key=f"enrich_{lead['id']}", type="primary", width="stretch",
                     help="Finds the website and the email, checks it, then reads recent company news. About a minute."):
            run_enrichment([lead["id"]])

def status_box(lead: dict) -> None:
    lead_id = lead["id"]
    with st.container(border=True):
        st.markdown("#### Status")
        if lead["first_email_on"]:
            done = [f"First email {nice(lead['first_email_on'])}"] + \
                   [f"Follow-up {i} {nice(d)}" if i <= 2 else f"Check-in {nice(d)}"
                    for i, d in enumerate(lead["follow_ups_on"], start=1)]
            st.markdown(" · ".join(done) + (f"  \n{next_step_tag(lead)}" if lead["next_label"] else ""),
                        unsafe_allow_html=True)
        else:
            st.caption("You send from Outlook, so log each email here with the day it went out. The card moves by itself.")
        c1, c2 = st.columns([2, 3])
        when = c1.date_input("Date", value=date.today(), max_value=date.today(), key=f"when_{lead_id}",
                             format="DD/MM/YYYY")
        note = c2.text_input("Note (optional)", key=f"note_{lead_id}", placeholder="e.g. what they replied")
        if not lead["first_email_on"]:
            send_event, send_label = "sent", "First email sent"
        else:
            send_event, send_label = "follow_up", (lead["next_label"] or "Follow-up") + " sent"
        b = st.columns(3)
        if b[0].button(send_label, key=f"ev_send_{lead_id}", type="primary", width="stretch",
                       disabled=lead["stage"] in ("Replied", "Not a fit")):
            data.add_event(lead_id, send_event, note, when)
            st.rerun()
        if b[1].button("Log a reply", key=f"ev_reply_{lead_id}", width="stretch"):
            data.add_event(lead_id, "replied", note, when)
            st.rerun()
        fit_event = "reopened" if lead["stage"] == "Not a fit" else "not_fit"
        if b[2].button("Reopen" if fit_event == "reopened" else "Not a fit", key=f"ev_fit_{lead_id}", width="stretch"):
            data.add_event(lead_id, fit_event, note, when)
            st.rerun()

def timeline_box(lead: dict) -> None:
    with st.container(border=True):
        st.markdown("#### Timeline")
        items = [(lead["created_at"], "Lead created", None)]
        o = lead["outreach"]
        for key, label in (("sent_at", "First email sent (before the console)"),
                           ("follow_up_sent_at", "Follow-up sent (before the console)"), ("replied_at", "Reply received")):
            if o.get(key):
                items.append((o[key], label, None))
        for e in lead["events"]:
            when = e.get("happened_on") or e["created_at"]
            items.append((when, data.EVENTS.get(e["event"], e["event"]) + (f": {e['note']}" if e["note"] else ""), e["id"]))
        for at, text, event_id in sorted((i for i in items if i[0]), key=lambda i: str(i[0]), reverse=True):
            c1, c2 = st.columns([6, 1])
            c1.markdown(f"<span class='small'>{nice(str(at))}</span> · {text}", unsafe_allow_html=True)
            if event_id and c2.button("Undo", key=f"undo_{event_id}"):
                data.undo_event(event_id)
                st.rerun()
#--------------------------------------------------------------#

def enrichment_box(lead: dict) -> None:
    with st.container(border=True):
        st.markdown("#### Enrichment")
        if lead["contact_email"]:
            st.markdown(f"**{lead['contact_name'] or 'Contact'}**" + (f" · {lead['contact_title']}" if lead["contact_title"] else ""))
            st.markdown(f"`{lead['contact_email']}` {email_tag(lead['email_status'])}", unsafe_allow_html=True)
            how = lead["email_method"] or lead["contact_source"] or ""
            src = f" · [where]({lead['email_source']})" if (lead["email_source"] or "").startswith("http") else ""
            st.caption(f"How it was found: {how}{src}")
        else:
            st.caption(f"No email yet. Status: {lead['email_status'] or 'not enriched yet'}"
                       f"{' · tries so far: ' + str(lead['enrich_attempts']) if lead['enrich_attempts'] else ''}")
        if lead["contact_linkedin"]:
            st.markdown(f"[LinkedIn profile]({lead['contact_linkedin']})")
        if lead["extra_email"]:
            st.markdown("**Second contact**")
            st.markdown(f"{lead['extra_name'] or ''}" + (f" · {lead['extra_title']}" if lead["extra_title"] else ""))
            st.markdown(f"`{lead['extra_email']}` {email_tag(lead['extra_email_status'])}", unsafe_allow_html=True)
        if lead["domain"]:
            st.markdown(f"**Website:** [{lead['domain']}](https://{lead['domain']})"
                        + (" (uncertain)" if lead["domain_status"] == "uncertain" else ""))
        crawl = lead["crawl"]
        if crawl:
            st.caption(f"Crawled {data.ago(crawl['crawled_at'])}: {crawl['pages'] or 0} pages, status {crawl['status']}")
            named = [p for p in crawl["people"] if isinstance(p, dict) and p.get("name")]
            if named:
                st.markdown("**People on the website**")
                for p in named[:8]:
                    link = f" · [source]({p['source_url']})" if p.get("source_url") else ""
                    st.markdown(f"- {p['name']}" + (f", {p.get('role')}" if p.get("role") else "") + link)
        generic = [e for e in lead["site_emails"] if e["is_generic"]]
        if generic:
            st.markdown("**General addresses:** " + ", ".join(f"`{e['email']}`" for e in generic[:4]))

def research_box(lead: dict) -> None:
    with st.container(border=True):
        st.markdown("#### Research notes")
        run = lead["research_run"]
        if not run:
            st.caption("Company updates from the last 3 months. Read once an email is found.")
        else:
            st.caption(f"Website read {data.ago(run['ran_at'])}: {run['pages_read']} recent pages, "
                       f"{run['status']}. Next check {nice(run['next_at'])}.")
        for n in lead["research"]:
            st.markdown(f"<span class='small'>{nice(n['published_at'])}</span> <span class='tag'>{n['label']}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"[{n['title'] or n['url'][:70]}]({n['url']})")
            if n["snippet"] and n["snippet"] != n["title"]:
                st.caption(n["snippet"])
#--------------------------------------------------------------#

def detail(lead_id: int) -> None:
    lead = data.lead_detail(lead_id)
    st.button("← All leads", on_click=close_lead)
    if not lead:
        st.warning("This lead isn't in the console.")
        return
    show_enrich_result()
    st.title(lead["company_name"])
    st.markdown(f"<span class='tag'>{lead['stage']}</span> <span class='tag grey'>{lead['market']} · "
                f"{lead['country'] or '?'}</span> <span class='tag grey'>priority {lead['priority'] or '?'}</span>",
                unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("#### Why now")
            st.write(lead["latest_signal"] or "")
            for p in lead["postings"]:
                st.markdown(f"**[{p['title']}]({p['url']})** · {p['location'] or ''} · {nice(p['posted_at'])}")
                if p["reason"]:
                    st.caption(p["reason"])
                if p["description"]:
                    with st.expander("Job description"):
                        st.write(p["description"][:4000])
            if not lead["postings"]:
                for link in data._split_links(lead["links"]):
                    st.markdown(f"[{link[:80]}]({link})")
        status_box(lead)
        timeline_box(lead)
    with right:
        contact_box(lead)
        enrichment_box(lead)
        research_box(lead)
        if lead["sheet"]:
            with st.expander("From the old Google Sheet"):
                for tab, cells in lead["sheet"].items():
                    st.markdown(f"**{tab}**")
                    st.dataframe(pd.DataFrame({"Column": list(cells), "Value": list(cells.values())}),
                                 hide_index=True, width="stretch")
#--------------------------------------------------------------#

# Page
lead_param = st.query_params.get("lead")
if lead_param and lead_param.isdigit():
    detail(int(lead_param))
    st.stop()

st.title("Leads")
st.caption("Every company hiring for the roles we watch, in every market.")
show_enrich_result()
market = market_filter("leads_market")
c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
search = c1.text_input("Search", placeholder="Company, role or email", label_visibility="collapsed")
view = c2.segmented_control("View", ["Board", "Table"], default="Board", label_visibility="collapsed") or "Board"
options = ["All stages"] + data.STAGES + ["Not a fit"]
stage_filter = c3.selectbox("Stage", options, label_visibility="collapsed",
                            index=options.index(st.session_state.pop("stage_filter", "All stages")))

leads = [l for l in data.leads() if in_market(l, market)]
if search:
    s = search.lower()
    leads = [l for l in leads if s in " ".join(str(l[k] or "") for k in
             ("company_name", "latest_signal", "contact_email", "contact_name", "domain")).lower()]
if stage_filter != "All stages":
    leads = column_order(stage_filter, [l for l in leads if l["stage"] == stage_filter])
else:
    leads = [l for l in leads if l["stage"] != "Not a fit"]
c4.caption(f"{len(leads)} leads")

if view == "Table" or stage_filter != "All stages":
    table(leads)
else:
    board(leads)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
