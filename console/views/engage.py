#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: console/views/engage.py
# Purpose: posts worth commenting on this week (from content-suggester), with a suggested angle.
#          The team comments by hand, then marks the post done or skips it.
#--------------------------------------------------------------#

# Imports libraries
import streamlit as st
import console_data as data
#--------------------------------------------------------------#

# Global variables
SHOW = 40
PLATFORMS = {"linkedin": "LinkedIn", "sap_community": "SAP Community", "reddit": "Reddit", "x": "X"}
#--------------------------------------------------------------#

def post_card(p: dict, tab: str) -> None:
    with st.container(border=True):
        who = p["author_name"] or p["author_handle"] or "Unknown author"
        st.markdown(f"**{who}** <span class='small'>· {PLATFORMS.get(p['platform'], p['platform'])} · "
                    f"{(p['posted_at'] or p['created_at'] or '')[:10]}</span>"
                    + (f" <span class='tag'>{p['kind']}</span>" if p["kind"] else ""), unsafe_allow_html=True)
        text = (p["text"] or "").strip()
        st.write(text[:420] + ("…" if len(text) > 420 else ""))
        if p["comment_angle"]:
            st.markdown(f"<span class='small'><b>Angle:</b> {p['comment_angle']}</span>", unsafe_allow_html=True)
        a, b, c = st.columns(3)
        a.link_button("Open post", p["url"], width="stretch")
        if p["action"]:
            if b.button("Undo", key=f"undo_{tab}_{p['item_id']}", width="stretch"):
                data.mark_post(p["item_id"], None)
                st.rerun()
        else:
            if b.button("Mark done", key=f"done_{tab}_{p['item_id']}", width="stretch"):
                data.mark_post(p["item_id"], "done")
                st.rerun()
            if c.button("Skip", key=f"skip_{tab}_{p['item_id']}", width="stretch"):
                data.mark_post(p["item_id"], "skipped")
                st.rerun()
#--------------------------------------------------------------#

st.title("Engage")
st.caption("Posts worth a comment this week. Comment by hand, then mark them done.")
posts = data.engage_posts()
todo = [p for p in posts if not p["action"]]
groups = {
    f"To do ({len(todo)})": todo,
    "Questions": [p for p in todo if p["kind"] == "Question"],
    "Pain points": [p for p in todo if p["kind"] == "Pain point"],
    "Done": [p for p in posts if p["action"] == "done"],
    "Skipped": [p for p in posts if p["action"] == "skipped"],
}
for tab, (name, items) in zip(st.tabs(list(groups)), groups.items()):
    with tab:
        if not items:
            st.info("Nothing here.")
        left, right = st.columns(2)
        for i, p in enumerate(items[:SHOW]):
            with (left if i % 2 == 0 else right):
                post_card(p, name.split(" ")[0])
        if len(items) > SHOW:
            st.caption(f"Showing {SHOW} of {len(items)}.")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
