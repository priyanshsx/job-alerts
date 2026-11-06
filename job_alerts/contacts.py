#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/contacts.py
# Purpose: the Monday "contacts" command. Only for rows ticked in the sheet:
#          Leads tab, "Find contact" ticked  -> find the company's domain, the most relevant
#                                               person, and their email
#          People tab, "Find email" ticked   -> find that person's email
#          Syncs before (to read the ticks) and after (to show the results). Nothing is
#          ever looked up twice, so re-running is safe.
#--------------------------------------------------------------#

# Imports libraries
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel
from job_alerts.core.config import load_config
from job_alerts.core.db import get_conn, get_client_id
from job_alerts.core.llm import call_llm
from job_alerts.core.names import normalize_name
from job_alerts.emails import apollo, hunter, prospeo
from job_alerts.emails.base import ProviderUnavailable
from job_alerts.people_sync import people_sync
from job_alerts.sources import web_search, xray_search
from job_alerts.sources.xray_search import normalize_linkedin_url
from job_alerts.sync import sync
#--------------------------------------------------------------#

# Global variables
PROVIDERS = {apollo.NAME: apollo, prospeo.NAME: prospeo, hunter.NAME: hunter}
WAITING = "waiting for credits"   # no provider could be tried yet (missing keys or monthly limits reached)
NOT_COMPANY_SITES = ("linkedin.", "xing.", "facebook.", "instagram.", "twitter.", "x.com", "youtube.",
                     "wikipedia.", "northdata.", "kununu.", "indeed.", "stepstone.", "glassdoor.",
                     "arbeitsagentur.", "crunchbase.", "bloomberg.", "dnb.com", "zoominfo.",
                     "firmenwissen.", "unternehmensregister.", "monster.", "jobs.")
#--------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
#--------------------------------------------------------------#

# LLM answer shapes
class DomainPick(BaseModel):
    domain: str | None          # e.g. "rottendorf.de"; null if no result is clearly the company's own site
    confidence: Literal["high", "medium", "low"]

class ContactPick(BaseModel):
    url: str | None             # the chosen profile URL, exactly as given; null if no good match
    full_name: str | None = None
    title: str | None = None
    confidence: Literal["high", "medium", "low"]
    reason: str
#--------------------------------------------------------------#

DOMAIN_PROMPT = """Which of these search results is the official website of the company "{company}"{country}?
Answer with the website's domain only (for example "example.de"), taken from one of the URLs below.
If none of the results is clearly the company's own website (directories, job boards, news and
social networks don't count), answer null. Never invent a domain.

Results:
{results}"""

CONTACT_PROMPT = """You pick the best person to contact at a company for {display_name}.
About {display_name}: {positioning}

Company: {company}
Why the company is a lead: {signal}
Preferred roles, best first: {roles}

From the LinkedIn search results below, pick the one person who currently works at {company}
in the most suitable role (earlier in the list is better). Use only what the results say.
If nobody clearly works at {company} in a suitable role, answer url = null. Never pick
recruiters or people at other companies. Keep the url exactly as given.

Results:
{results}"""
#--------------------------------------------------------------#

# Find (or reuse) a company's website domain
def find_domain(conn, cfg, client_id: int, company: str, country: str | None) -> str | None:
    key = normalize_name(company)
    if not key:
        return None
    cached = conn.execute("SELECT domain FROM company_domains WHERE client_id = ? AND name_normalized = ?",
                          (client_id, key)).fetchone()
    if cached:
        return cached["domain"] or None

    results = [r for r in web_search.search(f"{company} official website", num=8)
               if r["url"] and not any(s in r["url"].lower() for s in NOT_COMPANY_SITES)]
    domain, source_url = None, None
    if results:
        pick = call_llm("find_domain", DOMAIN_PROMPT.format(
            company=company, country=f" ({country})" if country else "",
            results="\n".join(f"- {r['url']} | {r['title']}" for r in results)),
            DomainPick, client_id)
        hosts = {urlparse(r["url"]).netloc.lower().removeprefix("www."): r["url"] for r in results}
        candidate = (pick.domain or "").lower().strip().removeprefix("www.")
        if candidate and candidate in hosts and pick.confidence != "low":   # must be a real result
            domain, source_url = candidate, hosts[candidate]

    conn.execute("INSERT INTO company_domains (client_id, name_normalized, domain, source_url, checked_at) "
                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT (client_id, name_normalized) DO UPDATE SET "
                 "domain = excluded.domain, source_url = excluded.source_url, checked_at = excluded.checked_at",
                 (client_id, key, domain or "", source_url, _now()))
    return domain
#--------------------------------------------------------------#

# Find the most relevant person at a lead's company
def find_contact(cfg, client_id: int, lead, roles: list[str], max_searches: int) -> dict | None:
    company = lead["company_name"]
    for role in roles[:max_searches]:
        results = xray_search.search(f"{role} {company}")
        if not results:
            continue
        pick = call_llm("find_contact", CONTACT_PROMPT.format(
            display_name=cfg.display_name, positioning=cfg.positioning.strip(), company=company,
            signal=lead["latest_signal"] or "", roles=", ".join(roles),
            results="\n".join(f"- url: {r['url']}\n  title: {r['title']}\n  snippet: {r['snippet']}"
                              for r in results)),
            ContactPick, client_id, max_tokens=800)
        urls = {r["url"] for r in results}
        if pick.url and normalize_linkedin_url(pick.url) in urls and pick.confidence != "low":
            return {"linkedin_url": normalize_linkedin_url(pick.url), "full_name": pick.full_name,
                    "title": pick.title, "company_name": company, "reason": pick.reason}
    return None
#--------------------------------------------------------------#

# Credits used this month per provider (from the lookup log)
def credits_used(conn, provider: str) -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    row = conn.execute("SELECT COALESCE(SUM(credits), 0) FROM email_lookups WHERE provider = ? "
                       "AND substr(created_at, 1, 7) = ?", (provider, month)).fetchone()
    return row[0]
#--------------------------------------------------------------#

# The email waterfall: try providers in order, stop at the first verified email
def find_email(conn, client_id: int, person: dict, domain: str | None, providers: list[dict],
               unavailable: set[str]) -> tuple[str | None, str, str | None]:
    best = (None, "not_found", None)
    tried = False
    for p in providers:
        name, limit = p["name"], p.get("monthly_limit", 0)
        module = PROVIDERS.get(name)
        if not module or name in unavailable or credits_used(conn, name) >= limit:
            continue
        try:
            result = module.find(person, domain)
        except ProviderUnavailable as e:
            unavailable.add(name)
            print(f"    {name} skipped: {e}")
            continue
        except Exception as e:                       # network trouble: log and try the next provider
            result_status, detail = "error", str(e)[:200]
            conn.execute("INSERT INTO email_lookups (client_id, person_id, provider, result, credits, "
                         "detail, created_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
                         (client_id, person.get("id"), name, result_status, detail, _now()))
            continue
        tried = True                                 # a provider actually answered
        conn.execute("INSERT INTO email_lookups (client_id, person_id, provider, result, email, "
                     "email_status, credits, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (client_id, person.get("id"), name, "found" if result.email else result.status,
                      result.email, result.status, result.credits, result.detail, _now()))
        if result.email and result.status == "verified":
            return result.email, "verified", name
        if result.email and best[0] is None:
            best = (result.email, result.status, name)   # keep a risky email as a fallback
    if not tried and best[0] is None:
        return None, WAITING, None                       # no keys or credits: try again next run
    return best
#--------------------------------------------------------------#

# Add (or reuse) the contact in the people table, so outreach is tracked in the People tab
def save_contact_person(conn, client_id: int, contact: dict, lead) -> int:
    conn.execute(
        """INSERT INTO people (client_id, full_name, title, company_name, linkedin_url, source,
           reason, priority, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'lead_contact', ?, 1, 'sent', ?)
           ON CONFLICT (client_id, linkedin_url) DO NOTHING""",
        (client_id, contact["full_name"], contact["title"], contact["company_name"],
         contact["linkedin_url"], f"Contact for lead: {lead['latest_signal'] or lead['company_name']}",
         _now()))
    return conn.execute("SELECT id FROM people WHERE client_id = ? AND linkedin_url = ?",
                        (client_id, contact["linkedin_url"])).fetchone()["id"]
#--------------------------------------------------------------#

# The command
def contacts(client: str) -> None:
    sync(client)                                     # read Monday's ticks from the sheet
    people_sync(client)

    cfg = load_config(client)
    settings = getattr(cfg, "contacts", None) or {}
    roles_default = settings.get("default_roles", [])
    max_searches = settings.get("max_role_searches", 3)
    providers = settings.get("email_providers", [])
    warn_remaining = settings.get("warn_remaining", 20)
    unavailable: set[str] = set()

    conn = get_conn()
    client_id = get_client_id(conn, client)
    stats = {"leads": 0, "contacts": 0, "lead_emails": 0, "people": 0, "people_emails": 0}
    #--------------------------------------------------------------#

    # 1. Leads ticked "Find contact"
    leads = conn.execute("SELECT * FROM leads WHERE client_id = ? AND find_contact = 1 "
                         "AND (contact_checked_at IS NULL OR email_status = ?)",
                         (client_id, WAITING)).fetchall()
    for lead in leads:
        stats["leads"] += 1
        print(f"  lead: {lead['company_name']}")
        domain = lead["domain"] or find_domain(conn, cfg, client_id, lead["company_name"], lead["country"])
        if lead["contact_person_id"]:                # contact found on an earlier run: only the email is left
            contact = {"linkedin_url": lead["contact_linkedin"], "full_name": lead["contact_name"],
                       "title": lead["contact_title"], "company_name": lead["company_name"]}
        else:
            roles = ([lead["contact_role"]] if lead["contact_role"] else []) + \
                    [r for r in roles_default if r != lead["contact_role"]]
            contact = find_contact(cfg, client_id, lead, roles, max_searches)
        email, status, person_id = None, "not_found", lead["contact_person_id"]
        if contact:
            stats["contacts"] += 1
            person_id = person_id or save_contact_person(conn, client_id, contact, lead)
            email, status, source = find_email(conn, client_id, {**contact, "id": person_id},
                                               domain, providers, unavailable)
            if email:
                stats["lead_emails"] += 1
            conn.execute("UPDATE people SET email = ?, email_status = ?, email_source = ?, "
                         "email_checked_at = ? WHERE id = ?",
                         (email, status, source, None if status == WAITING else _now(), person_id))
            print(f"    contact: {contact['full_name']} ({contact['title']}), email: {email or status}")
        else:
            print("    no suitable contact found")
        conn.execute(
            """UPDATE leads SET domain = ?, contact_person_id = ?, contact_name = ?, contact_title = ?,
               contact_linkedin = ?, contact_email = ?, email_status = ?, contact_checked_at = ?
               WHERE id = ?""",
            (domain, person_id, contact and contact["full_name"], contact and contact["title"],
             contact and contact["linkedin_url"], email, status if contact else "no contact found",
             _now(), lead["id"]))
        conn.commit()
    #--------------------------------------------------------------#

    # 2. People ticked "Find email"
    people = conn.execute("SELECT * FROM people WHERE client_id = ? AND find_email = 1 "
                          "AND email_checked_at IS NULL AND id NOT IN (SELECT contact_person_id FROM leads "
                          "WHERE client_id = ? AND contact_person_id IS NOT NULL)",
                          (client_id, client_id)).fetchall()
    for person in people:
        stats["people"] += 1
        print(f"  person: {person['full_name']} ({person['company_name']})")
        domain = find_domain(conn, cfg, client_id, person["company_name"], None) \
            if person["company_name"] else None
        email, status, source = find_email(conn, client_id, dict(person), domain, providers, unavailable)
        if email:
            stats["people_emails"] += 1
        conn.execute("UPDATE people SET email = ?, email_status = ?, email_source = ?, "
                     "email_checked_at = ? WHERE id = ?",
                     (email, status, source, None if status == WAITING else _now(), person["id"]))
        conn.commit()
        print(f"    email: {email or status}")
    #--------------------------------------------------------------#

    # Summary and credit warnings
    print(f"[{client}] contacts: {stats['leads']} leads checked, {stats['contacts']} contacts found, "
          f"{stats['lead_emails']} lead emails; {stats['people']} people checked, "
          f"{stats['people_emails']} emails")
    for p in providers:
        used = credits_used(conn, p["name"])
        left = p.get("monthly_limit", 0) - used
        flag = "  <- running low" if left <= warn_remaining else ""
        state = " (not available: check its API key or plan)" if p["name"] in unavailable else ""
        print(f"    {p['name']:<8} {used} used, {left} left this month{flag}{state}")
    conn.close()

    sync(client)                                     # show the results in the sheet
    people_sync(client)
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
