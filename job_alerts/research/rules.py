#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/research/rules.py
# Purpose: match pages against the client's events (config: research.events). No LLM.
#          A keyword matches as a whole word or phrase; "word*" matches anything starting with it.
#          Points = event points, +25% per extra keyword (up to 3), x1.25 if it's in the title,
#          halved every half_life_days of age.
#--------------------------------------------------------------#

# Imports libraries
import re
from datetime import date, datetime, timezone
#--------------------------------------------------------------#

# Global variables
MATCH_CHARS = 4000                     # only the start of a page counts (the article, not "related news")
SNIPPET_CHARS = 260
#--------------------------------------------------------------#

def _pattern(keyword: str) -> re.Pattern:
    word = keyword.strip().lower()
    prefix = word.endswith("*")
    body = re.escape(word.rstrip("*")).replace(r"\ ", r"[\s\-]+")
    word = word.rstrip("*")
    head = r"(?<!\w)" if re.match(r"\w", word) else ""
    tail = r"[\w-]*" if prefix else (r"(?!\w)" if re.search(r"\w$", word) else "")
    return re.compile(head + body + tail, re.IGNORECASE)

# research.events -> [{"key", "label", "points", "patterns": [(keyword, pattern)]}]
def compile_events(events: dict) -> list[dict]:
    out = []
    for key, ev in (events or {}).items():
        words = [w for lang in (ev.get("keywords") or {}).values() for w in (lang or [])]
        out.append({"key": key, "label": ev.get("label", key), "points": float(ev.get("points", 10)),
                    "patterns": [(w, _pattern(w)) for w in dict.fromkeys(words)]})
    return out
#--------------------------------------------------------------#

def snippet(text: str, position: int) -> str:
    """The sentence around a position, at most SNIPPET_CHARS."""
    start = max(text.rfind(". ", 0, position), text.rfind("\n", 0, position)) + 1
    ends = [i for i in (text.find(". ", position), text.find("\n", position)) if i != -1]
    end = min(ends) + 1 if ends else len(text)
    piece = text[start:end].strip()
    if len(piece) > SNIPPET_CHARS:
        offset = max(0, position - start - SNIPPET_CHARS // 3)
        piece = ("…" if offset else "") + piece[offset:offset + SNIPPET_CHARS].strip() + "…"
    return piece

# Matches for one page: [{"event", "label", "points", "matched", "snippet"}], best first
def match_page(page: dict, events: list[dict], half_life_days: float, today: date | None = None) -> list[dict]:
    title = page.get("title") or ""
    body = (page.get("text") or "")[:MATCH_CHARS]
    rest = body.replace(title, " " * len(title), 1) if title and title in body else body   # snippet from the article, not its heading
    today = today or datetime.now(timezone.utc).date()
    try:
        age = (today - date.fromisoformat(page["published_at"][:10])).days
    except (KeyError, TypeError, ValueError):
        age = 0
    decay = 0.5 ** (max(0, age) / max(1.0, half_life_days))
    out = []
    for ev in events:
        hits, first, in_title = [], None, False
        for word, pattern in ev["patterns"]:
            mt = pattern.search(title)
            mb = pattern.search(body)
            if mt or mb:
                hits.append(word)
                in_title = in_title or bool(mt)
                mr = pattern.search(rest)
                if mr and (first is None or mr.start() < first):
                    first = mr.start()
        if not hits:
            continue
        points = ev["points"] * (1 + 0.25 * (min(len(hits), 3) - 1)) * (1.25 if in_title else 1) * decay
        out.append({"event": ev["key"], "label": ev["label"], "points": round(points, 1),
                    "matched": ", ".join(hits[:6]),
                    "snippet": snippet(body, first) if first is not None else title})
    return sorted(out, key=lambda m: m["points"], reverse=True)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
