#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# Imports libraries
import time
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.llm import call_llm
from job_alerts.sources import xray_search
from job_alerts.sources.xray_search import normalize_linkedin_url
#--------------------------------------------------------------#

# Global variables and classes 
SITE = ""

class Person(BaseModel):
    url: str
    full_name: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    is_match: bool
    reason: str

class ParsedResults(BaseModel):
    people: list[Person]
#--------------------------------------------------------------#

# Prompt for AI call
PARSE_PROMPT = """
                You read LinkedIn profile search results for {display_name}.
                {display_name} wants to connect with people in these roles: {titles}.
                About {display_name}: {positioning}
                {company_context}

                For each result, extract the person's name, current title, company and location from the
                result title and snippet. Use only what the text says. If something isn't stated, use null.
                Never add people who are not in the results.

                is_match: true only if the person's CURRENT title matches one of the target roles or a close
                equivalent (including German titles), and they don't work for a staffing or recruitment agency.
                reason: one short sentence on why this person is worth connecting with, in English.
                Keep each url exactly as given.

                Results: {results}
"""
#--------------------------------------------------------------#

def _now() -> datetime:
    return datetime.now(timezone.utc)
#--------------------------------------------------------------#

def _build_queries(cfg, conn, client_id) -> list[tuple[str, int, str | None]]:
    """Return (query, priority, company) tuples, most valuable first."""
    pf = cfg.people_finder
    titles = pf["titles"]
    queries = []
#--------------------------------------------------------------#
    # 1. Target titles at companies from recent job alerts: each person comes with a reason
    if pf.get("from_job_alerts", True):
        since = (_now() - timedelta(days=14)).isoformat()
        companies = conn.execute(
            "SELECT DISTINCT company_name FROM job_postings WHERE client_id = ? "
            "AND is_relevant = 1 AND priority <= 2 AND created_at >= ? "
            "AND company_name IS NOT NULL",
            (client_id, since),
        ).fetchall()
        title_terms = " OR ".join(f'"{t}"' for t in titles)
        for row in companies:
            queries.append((f'{SITE} "{row["company_name"]}" ({title_terms})'.strip(), 1, row["company_name"]))
    #--------------------------------------------------------------#

    # 2. Titles × locations: broader reach
    for title in titles:
        for location in pf.get("locations", []):
            queries.append((f'{SITE} "{title}" "{location}"'.strip(), 2, None))
    #--------------------------------------------------------------#

    # Skip searches that ran recently, so each week brings new people
    cutoff = (_now() - timedelta(days=pf.get("search_cooldown_days", 30))).isoformat()
    recent = {r["query"] for r in conn.execute(
        "SELECT query FROM people_searches WHERE client_id = ? AND run_at >= ?",
        (client_id, cutoff),
    )}
    queries = [q for q in queries if q[0] not in recent]
    return queries[: pf.get("max_searches_per_run", 30)]
#--------------------------------------------------------------#

def find_people(client: str) -> None:
    cfg = load_config(client)
    pf = cfg.people_finder
    conn = get_conn()
    client_id = get_client_id(conn, client)

    queries = _build_queries(cfg, conn, client_id)
    print(f"[{client}] running {len(queries)} searches")

    new = 0
    for i, (query, priority, company) in enumerate(queries, start=1):
        try:
            results = xray_search.search(query)
        except Exception as e:
            print(f"  search failed: {query} ({e})")
            continue

        conn.execute(
            "INSERT INTO people_searches (client_id, query, results, run_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (client_id, query) DO UPDATE SET results = excluded.results, run_at = excluded.run_at",
            (client_id, query, len(results), _now().isoformat()),
        )
        conn.commit()

        # Only send people we haven't seen to the LLM, to save cost
        known = {r["linkedin_url"] for r in conn.execute(
            "SELECT linkedin_url FROM people WHERE client_id = ?", (client_id,))}
        fresh = [r for r in results if r["url"] not in known]
        if not fresh:
            continue

        company_context = (
            f"These results are for people at {company}, which recently posted a relevant job."
            if company else ""
        )
        prompt = PARSE_PROMPT.format(
            display_name=cfg.display_name,
            titles=", ".join(pf["titles"]),
            positioning=cfg.positioning.strip(),
            company_context=company_context,
            results="\n".join(
                f"- url: {r['url']}\n  title: {r['title']}\n  snippet: {r['snippet']}" for r in fresh
            ),
        )
        try:
            parsed = call_llm("parse_people", prompt, ParsedResults, client_id)
        except RuntimeError as e:
            print(f"  parse failed: {query} ({e})")
            continue

        fresh_urls = {r["url"] for r in fresh}
        for p in parsed.people:
            url = normalize_linkedin_url(p.url)
            if not p.is_match or url not in fresh_urls:   # ignore anything not in the actual results
                continue
            cur = conn.execute(
                """INSERT INTO people (client_id, full_name, title, company_name, location,
                   linkedin_url, source, query, reason, priority, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (client_id, linkedin_url) DO NOTHING""",
                (client_id, p.full_name, p.title, p.company or company, p.location, url,
                 "job_alerts_company" if company else "title_search",
                 query, p.reason, priority, _now().isoformat()),
            )
            new += cur.rowcount
        conn.commit()
        print(f"  {i}/{len(queries)}  {len(fresh)} results, {new} new people so far")
        time.sleep(1)

    conn.close()
    print(f"[{client}] added {new} new people")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#