#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/enrich.py
# Purpose: the enrichment crawler. Runs from cron every 10 minutes for all clients:
#            python3 -m job_alerts enrich --all
#          Each run:
#            1. syncs every client's Leads tab (contacts and domains you typed) and reads its
#               Manual Lookup tab -> leads
#            2. takes the leads that are due, newest first, mixed across clients, for up to --minutes
#            3. per lead: domain (free methods first) -> crawl the company website (free) ->
#               email for the lead's contact, plus a second person from the website (e.g. the
#               managing director) -> MillionVerifier -> Leads tab
#            4. syncs the Leads tab of every client that changed
#          A lead without an email is tried again after 1, 3, 7 and 30 days, then monthly.
#          Apollo, Prospeo and Hunter are never used here.
#--------------------------------------------------------------#

# Imports libraries
import fcntl
import time
from datetime import datetime, timedelta, timezone
from job_alerts.core import usage
from job_alerts.core.config import load_config
from job_alerts.core.db import ROOT, get_conn, get_client_id
from job_alerts.core.names import normalize_name
from job_alerts.crawler import domains, finder, site
#--------------------------------------------------------------#

# Global variables
BACKOFF_DAYS = [1, 3, 7, 30]               # after that: every 30 days
DONE = "9999-12-31"                        # enrich_next_at for a finished lead
FOUND = ("verified", "catch-all", "catch-all (guess)")
SKIP_STATUSES = {"rejected", "not a fit", "not relevant", "lost", "closed", "do not contact", "dnc", "no fit"}
LOCK_FILE = ROOT / "data" / "enrich.lock"
NEW_EMAILS: set[int] = set()               # leads that got a new email in this run (moved to row 2 on sync)
SITE_PEOPLE_TRIED = 2                      # website people tried per lead
SITE_PERSON_GUESSES = 2                    # common formats tried for a website person when no format is known
#--------------------------------------------------------------#

def _now() -> datetime:
    return datetime.now(timezone.utc)
#--------------------------------------------------------------#

# Clients with a sheet and enrichment not switched off (enrich: {enabled: false} in the config)
def enabled_clients() -> list[str]:
    out = []
    for folder in sorted((ROOT / "config" / "clients").iterdir()):
        if not (folder / "config.yaml").exists():
            continue
        try:
            cfg = load_config(folder.name)
        except Exception as e:
            print(f"[{folder.name}] config not loaded: {e}")
            continue
        if (getattr(cfg, "enrich", None) or {}).get("enabled", True) is False:
            continue
        if (getattr(cfg, "sheets", None) or {}).get("spreadsheet_id"):
            out.append(folder.name)
    return out
#--------------------------------------------------------------#

# MillionVerifier credits this client has left this month (shared with the contacts command)
def make_verifier(conn, cfg, client_id: int) -> finder.Verifier:
    from job_alerts.contacts import credits_used
    providers = (getattr(cfg, "contacts", None) or {}).get("email_providers", [])
    limit = next((p.get("monthly_limit", 0) for p in providers if p["name"] == "pattern"), 0)
    return finder.Verifier(conn, client_id, limit - credits_used(conn, "pattern", client_id))

def _roles(cfg) -> list[str]:
    return (getattr(cfg, "contacts", None) or {}).get("default_roles", [])
#--------------------------------------------------------------#

# Why a lead is skipped, or None
def _skip_reason(conn, client_id: int, lead) -> str | None:
    if (lead["status"] or "").strip().lower() in SKIP_STATUSES:
        return "skipped (lead status)"
    if lead["request_id"] and not lead["contact_person_id"] and \
            normalize_name(lead["company_name"]) != lead["name_normalized"]:
        return "reply via the post"
    types = [r["employer_type"] for r in conn.execute(
        "SELECT company_name, employer_type FROM job_postings WHERE client_id = ? AND employer_type IS NOT NULL",
        (client_id,)) if normalize_name(r["company_name"]) == lead["name_normalized"]]
    if types and all(t == "agency" for t in types):
        return "skipped (recruitment agency)"
    return None
#--------------------------------------------------------------#

# Save what we know about a lead and when to look again
def _save(conn, lead, fields: dict, finished: bool) -> None:
    attempts = (lead["enrich_attempts"] or 0) + 1
    wait = BACKOFF_DAYS[min(attempts - 1, len(BACKOFF_DAYS) - 1)]
    fields = {**fields, "enrich_attempts": attempts, "enriched_at": _now().isoformat(),
              "enrich_next_at": DONE if finished else (_now() + timedelta(days=wait)).isoformat()}
    conn.execute(f"UPDATE leads SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                 (*fields.values(), lead["id"]))
    conn.commit()
#--------------------------------------------------------------#

# Enrich one lead. Returns a short line for the log.
def enrich_lead(conn, cfg, client_id: int, lead_id: int, verifier: finder.Verifier | None = None) -> str:
    from job_alerts.contacts import find_domain
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    verifier = verifier or make_verifier(conn, cfg, client_id)
    roles = _roles(cfg)

    reason = _skip_reason(conn, client_id, lead)
    if reason:
        _save(conn, lead, {"email_status": lead["email_status"] or reason}, finished=True)
        return reason
    #--------------------------------------------------------------#

    # 1. Domain
    paid = lambda company, country: find_domain(conn, cfg, client_id, company, country)
    domain, d_status, d_source = domains.resolve(conn, client_id, lead, paid)
    fields = {"domain": domain, "domain_status": d_status, "domain_source": d_source}
    if not domain or d_status == "uncertain":
        status = "domain uncertain" if domain else "domain not found"
        _save(conn, lead, {**fields, "email_status": lead["contact_email"] and lead["email_status"] or status},
              finished=False)
        return f"{status} ({domain or '-'})"
    #--------------------------------------------------------------#

    # 2. Website evidence (free)
    info = site.crawl(conn, domain, roles)
    mail_dom = finder.mail_domain(domain, info["emails"], lead["company_name"], info.get("home_url"))
    #--------------------------------------------------------------#

    # 3. The lead's own contact (picked from LinkedIn) comes first
    has_contact = lead["contact_name"] and lead["contact_source"] != "website"
    already = lead["contact_email"] and lead["email_status"] in FOUND
    try:
        primary = None
        if has_contact and not already:
            primary = finder.find(conn, verifier, lead["contact_name"], mail_dom, info["emails"],
                                  lead["contact_person_id"])
            if primary["email"]:
                fields.update(contact_email=primary["email"], email_status=primary["status"],
                              email_method=primary["method"], email_source=primary["source"],
                              contact_source=lead["contact_source"] or "linkedin")
            elif not lead["contact_email"]:
                fields["email_status"] = primary["status"]

        # 4. A second person from the website (target role or legal representative); at most 2 tried
        person, second = None, None
        others = [p for p in site.ranked_people(info["people"], roles) if not has_contact or
                  normalize_name(p["name"]) != normalize_name(lead["contact_name"])]
        if lead["contact_source"] == "manual" or "manual_lookup" in (lead["sources"] or ""):
            others = []                              # you named the person: no extra website guesses
        for candidate in others[:SITE_PEOPLE_TRIED]:
            own = next((e for e in info["emails"] if e["name"] and
                        normalize_name(e["name"]) == normalize_name(candidate["name"])), None)
            person = candidate
            second = finder.find(conn, verifier, candidate["name"], mail_dom, info["emails"], None,
                                 common=SITE_PERSON_GUESSES, own_email=own and own["email"],
                                 own_source=own and own["source_url"])
            if second["email"]:
                break
    except finder.OutOfCredits:
        _save(conn, lead, {**fields, "email_status": lead["email_status"] if already else "waiting for credits"},
              finished=False)
        return "waiting for MillionVerifier credits"
    #--------------------------------------------------------------#

    # 5. Who goes where: the LinkedIn contact first; the website person second, or alone if there's no contact
    if second and second["email"]:
        if has_contact:
            fields.update(extra_name=person["name"], extra_title=person["role"], extra_email=second["email"],
                          extra_email_status=second["status"])
        elif not (lead["contact_source"] == "website" and already):
            fields.update(contact_name=person["name"], contact_title=person["role"], contact_email=second["email"],
                          email_status=second["status"], email_method=second["method"],
                          email_source=second["source"], contact_source="website")
    if not has_contact and not lead["contact_email"] and not fields.get("contact_email"):
        fields["email_status"] = "unresolved (no named person found)" if not person else \
            (second or {}).get("status", "unresolved")

    if fields.get("contact_email") or fields.get("extra_email"):
        NEW_EMAILS.add(lead["id"])
    final_status = fields.get("email_status", lead["email_status"])
    finished = final_status in FOUND
    _save(conn, lead, fields, finished=finished)
    main = fields.get("contact_email") or lead["contact_email"]
    extra = f"; {fields['extra_email']}" if fields.get("extra_email") else ""
    fmt, _ = finder.known_format(conn, mail_dom, info["emails"])
    named = sum(1 for e in info["emails"] if e.get("name"))
    detail = (f" [{info.get('pages', 0)} pages, {len(info['emails'])} emails ({named} named), "
              f"{len(info['people'])} people, mail {mail_dom}, format {fmt or 'unknown'}"
              f"{', tried ' + person['name'] if person else ''}]")
    return f"{domain} ({d_source}): {main or final_status}{extra}{detail}"
#--------------------------------------------------------------#

# Leads due now for one client, newest first
def due_leads(conn, client_id: int) -> list[int]:
    rows = conn.execute("SELECT id FROM leads WHERE client_id = ? AND (enrich_next_at IS NULL OR enrich_next_at <= ?) "
                        "AND company_name IS NOT NULL AND company_name != '' "
                        "ORDER BY enrich_next_at IS NOT NULL, priority, created_at DESC",
                        (client_id, _now().isoformat())).fetchall()
    return [r["id"] for r in rows]
#--------------------------------------------------------------#

# The cron command. clients: None = all enabled clients. lead_ids: only these (Manual Lookup).
def run(clients: list[str] | None = None, minutes: float = 8, lead_ids: dict[str, list[int]] | None = None) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"enrich: another run is still busy ({_now():%H:%M} UTC), skipping")
        return

    from job_alerts import manual_lookup
    from job_alerts.sync import sync
    deadline = time.time() + minutes * 60
    conn = get_conn()
    queues, ctx = {}, {}
    for client in clients or enabled_clients():
        try:
            cfg = load_config(client)
            client_id = get_client_id(conn, client)
            usage.set_context(client, "enrich")
            if lead_ids is None:
                sync(client)                         # pick up names and domains typed in the Leads tab
            if lead_ids is not None:                 # only the given leads (e.g. the lookup command)
                ids = lead_ids.get(client, [])
            else:
                ids = manual_lookup.run_lookups(conn, cfg, client_id)
                ids = list(dict.fromkeys(ids + due_leads(conn, client_id)))
            queues[client] = ids
            ctx[client] = (cfg, client_id, make_verifier(conn, cfg, client_id))
        except Exception as e:
            print(f"[{client}] enrich skipped: {e}")
    #--------------------------------------------------------------#

    changed, done = set(), 0
    while any(queues.values()) and time.time() < deadline:
        for client in list(queues):                  # one lead per client in turn
            if not queues[client] or time.time() >= deadline:
                continue
            lead_id = queues[client].pop(0)
            cfg, client_id, verifier = ctx[client]
            usage.set_context(client, "enrich")
            name = conn.execute("SELECT company_name FROM leads WHERE id = ?", (lead_id,)).fetchone()
            try:
                line = enrich_lead(conn, cfg, client_id, lead_id, verifier)
            except Exception as e:                   # one bad site never stops the run
                conn.rollback()
                line = f"error: {type(e).__name__}: {str(e)[:150]}"
                lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
                _save(conn, lead, {}, finished=False)
            print(f"[{client}] {name and name['company_name']}: {line}")
            changed.add(client)
            done += 1
    left = sum(len(q) for q in queues.values())
    conn2 = conn
    #--------------------------------------------------------------#

    for client in sorted(changed):
        try:
            client_id = ctx[client][1]
            moved = [r["id"] for r in conn2.execute(
                f"SELECT id FROM leads WHERE client_id = ? AND id IN ({','.join('?' * len(NEW_EMAILS))})",
                (client_id, *NEW_EMAILS))] if NEW_EMAILS else []
            sync(client, to_top=moved)
        except Exception as e:
            print(f"[{client}] sheet not updated: {e}")
    conn.close()
    print(f"enrich: {done} leads processed, {len(NEW_EMAILS)} new emails, {left} still due "
          f"({_now():%Y-%m-%d %H:%M} UTC)")
    lock.close()
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
