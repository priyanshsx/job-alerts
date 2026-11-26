#---------------------beginning-of-code------------------------#
#--------------------------------------------------------------#

# File: job_alerts/costs.py
# Purpose: the Costs tab in each client's Google Sheet: what the tools spent, per week and month,
#          in USD, EUR and INR, from sourcing to verified emails, plus what it produced and the
#          cost per lead, person, verified email and suggested thread.
#          Reads both tools' databases (job-alerts and content-suggester); the tab is rewritten on
#          every run and is read-only for the client.
#          Settings in .env (defaults in brackets):
#            FX_USD_INR (88.0), FX_EUR_INR (102.0)   exchange rates: update them now and then
#            LLM_COST_CURRENCY (INR)                 currency of LLM_PRICE_* in both .env files
#--------------------------------------------------------------#

# Imports libraries
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from job_alerts.core.config import load_config
from job_alerts.core.db import ROOT, get_conn, get_client_id
from job_alerts.core.sheets import open_worksheet
from job_alerts.hiring_leads import _suggester_db
#--------------------------------------------------------------#

# Global variables
load_dotenv(ROOT / ".env")
STAGES = ["leads", "people", "contacts", "content"]
STAGE_LABELS = {"leads": "Leads (sourcing + classification)", "people": "People finder",
                "contacts": "Contacts + emails", "content": "Content (posts + requests)"}
LLM_TASK_STAGE = {"classify_posting": "leads", "parse_people": "people",
                  "find_contact": "contacts", "find_domain": "contacts"}
COMMAND_STAGE = {"fetch": "leads", "describe": "leads", "classify": "leads", "run": "leads",
                 "people-find": "people", "people-run": "people", "contacts": "contacts"}
#--------------------------------------------------------------#

def _fx() -> tuple[float, float]:
    return float(os.getenv("FX_USD_INR") or 88.0), float(os.getenv("FX_EUR_INR") or 102.0)

def _llm_to_inr(amount: float, usd_inr: float) -> float:
    return amount * usd_inr if (os.getenv("LLM_COST_CURRENCY") or "INR").upper() == "USD" else amount

def _ts(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _week(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"

def _month(dt: datetime) -> str:
    return dt.strftime("%Y-%m")
#--------------------------------------------------------------#

# Collect (timestamp, INR) spend events per stage, and timestamps per volume metric
def _gather(client: str, conn, client_id: int, usd_inr: float):
    spend = {s: [] for s in STAGES}
    volume = {k: [] for k in ("postings_collected", "postings_classified", "leads_added", "people_added",
                              "contacts_found", "emails_verified", "emails_risky", "posts_collected",
                              "threads_suggested", "requests_found")}
    credits = []                                       # (timestamp, provider, credits)

    for task, cost, at in conn.execute("SELECT task, cost_usd, created_at FROM llm_calls WHERE client_id = ?",
                                       (client_id,)):
        stage = LLM_TASK_STAGE.get(task)
        if stage and _ts(at):
            spend[stage].append((_ts(at), _llm_to_inr(cost or 0, usd_inr)))
    try:
        for task, cost, at in conn.execute("SELECT task, cost_usd, created_at FROM api_calls WHERE client_id = ?",
                                           (client_id,)):
            stage = COMMAND_STAGE.get(task or "")
            if stage and _ts(at):
                spend[stage].append((_ts(at), (cost or 0) * usd_inr))
    except sqlite3.OperationalError:
        pass                                           # api_calls not created yet (migration 010)

    queries = {
        "postings_collected": "SELECT created_at FROM job_postings WHERE client_id = ?",
        "postings_classified": "SELECT classified_at FROM job_postings WHERE client_id = ? AND classified_at IS NOT NULL",
        "leads_added": "SELECT created_at FROM leads WHERE client_id = ?",
        "people_added": "SELECT created_at FROM people WHERE client_id = ? "
                        "AND COALESCE(source, '') NOT IN ('lead_contact', 'requester')",
        "contacts_found": "SELECT contact_checked_at FROM leads WHERE client_id = ? AND contact_person_id IS NOT NULL",
        "emails_verified": "SELECT created_at FROM email_lookups WHERE client_id = ? AND email_status = 'verified'",
        "emails_risky": "SELECT created_at FROM email_lookups WHERE client_id = ? AND email_status = 'risky'",
    }
    for key, sql in queries.items():
        volume[key] = [t for (at,) in conn.execute(sql, (client_id,)) if (t := _ts(at))]
    for provider, n, at in conn.execute("SELECT provider, credits, created_at FROM email_lookups "
                                        "WHERE client_id = ? AND credits > 0", (client_id,)):
        if _ts(at):
            credits.append((_ts(at), provider, n))

    # Content-suggester (posts, requests), read-only
    path = _suggester_db()
    content_found = path.exists()
    if content_found:
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = src.execute("SELECT id FROM clients WHERE name = ?", (client,)).fetchone()
            if row:
                cid = row[0]
                for cost, at in src.execute("SELECT cost_usd, created_at FROM llm_calls WHERE client_id = ?", (cid,)):
                    if _ts(at):
                        spend["content"].append((_ts(at), _llm_to_inr(cost or 0, usd_inr)))
                try:
                    for cost, at in src.execute("SELECT cost_usd, created_at FROM api_calls WHERE client_id = ?", (cid,)):
                        if _ts(at):
                            spend["content"].append((_ts(at), (cost or 0) * usd_inr))
                except sqlite3.OperationalError:
                    pass                               # api_calls not created yet (before the next content run)
                volume["posts_collected"] = [t for (at,) in src.execute(
                    "SELECT first_seen_at FROM items WHERE client_id = ?", (cid,)) if (t := _ts(at))]
                volume["threads_suggested"] = [t for (at,) in src.execute(
                    "SELECT created_at FROM suggestions WHERE client_id = ?", (cid,)) if (t := _ts(at))]
                volume["requests_found"] = [t for (at,) in src.execute(
                    "SELECT c.created_at FROM classifications c JOIN items i ON i.id = c.item_id "
                    "WHERE i.client_id = ? AND c.is_request = 1", (cid,)) if (t := _ts(at))]
        finally:
            src.close()
    return spend, volume, credits, content_found
#--------------------------------------------------------------#

# Build and write the Costs tab
def write_costs(client: str) -> None:
    cfg = load_config(client)
    sheets_cfg = getattr(cfg, "sheets", None) or {}
    if not sheets_cfg.get("spreadsheet_id"):
        print(f"[{client}] no sheets.spreadsheet_id in config, skipping costs")
        return
    usd_inr, eur_inr = _fx()
    conn = get_conn()
    client_id = get_client_id(conn, client)
    spend, volume, credits, content_found = _gather(client, conn, client_id, usd_inr)
    conn.close()

    now = datetime.now(timezone.utc)
    this_week, last_week = _week(now), _week(now - timedelta(days=7))
    this_month = _month(now)
    last_month = _month(now.replace(day=1) - timedelta(days=1))
    periods = {"This week": ("w", this_week), "Last week": ("w", last_week),
               "This month": ("m", this_month), "Last month": ("m", last_month)}

    def in_period(dt, period):
        kind, key = period
        return (_week(dt) if kind == "w" else _month(dt)) == key

    def stage_inr(stage, period):
        return sum(c for t, c in spend[stage] if in_period(t, period))

    def count(metric, period):
        return sum(1 for t in volume[metric] if in_period(t, period))

    def money(inr):                                    # INR -> (USD, EUR, INR)
        return [round(inr / usd_inr, 2), round(inr / eur_inr, 2), round(inr, 2)]
    #--------------------------------------------------------------#

    period_names = list(periods)                     # This week, Last week, This month, Last month
    rows, bold = [], []

    def title(text):
        rows.append([text]); bold.append(len(rows))

    def inr(x):
        return round(x, 2)

    totals = {p: sum(stage_inr(s, periods[p]) for s in STAGES) for p in period_names}
    title(f"Costs: {cfg.display_name}")
    all_events = [t for st in STAGES for t, _ in spend[st]]
    total_so_far = sum(c for st in STAGES for _, c in spend[st])
    since = f" (since {min(all_events):%d %b %Y})" if all_events else ""
    rows.append([f"Total spent so far{since}, in INR:", inr(total_so_far)]); bold.append(len(rows))
    rows.append([f"All amounts are in INR. Updated {now:%Y-%m-%d %H:%M} UTC. Actual tool costs only "
                 "(search APIs and AI); email lookups use free tiers."])
    if not content_found:
        rows.append(["Note: content-suggester's database wasn't found, so content costs are missing."])
    rows.append([])

    title("Spend (INR)")
    rows.append(["", *period_names]); bold.append(len(rows))
    rows.append(["Total", *[inr(totals[p]) for p in period_names]])
    for st in STAGES:
        rows.append([STAGE_LABELS[st], *[inr(stage_inr(st, periods[p])) for p in period_names]])
    rows.append([])

    title("Cost per result (INR)")
    rows.append(["", *period_names]); bold.append(len(rows))
    for label, stage, metric in [("Per lead added", "leads", "leads_added"),
                                 ("Per person found", "people", "people_added"),
                                 ("Per verified email", "contacts", "emails_verified"),
                                 ("Per suggested thread", "content", "threads_suggested")]:
        cells = []
        for p in period_names:
            n = count(metric, periods[p])
            cells.append(inr(stage_inr(stage, periods[p]) / n) if n else "-")
        rows.append([label, *cells])
    rows.append([])

    title("What it produced")
    rows.append(["", *period_names]); bold.append(len(rows))
    for label, metric in [("Job postings collected", "postings_collected"),
                          ("Job postings classified", "postings_classified"),
                          ("Leads added", "leads_added"), ("People found", "people_added"),
                          ("Contacts found", "contacts_found"), ("Verified emails", "emails_verified"),
                          ("Risky emails", "emails_risky"), ("Posts collected", "posts_collected"),
                          ("Threads suggested", "threads_suggested"), ("Requests found", "requests_found")]:
        rows.append([label, *[count(metric, periods[p]) for p in period_names]])
    rows.append([])

    title("Email credits this month (free tiers)")
    rows.append(["Provider", "Used", "Monthly budget", "Left"]); bold.append(len(rows))
    budgets = {p["name"]: p.get("monthly_limit", 0)
               for p in ((getattr(cfg, "contacts", None) or {}).get("email_providers") or [])}
    for provider, budget in budgets.items():
        used = sum(n for t, prov, n in credits if prov == provider and _month(t) == this_month)
        rows.append([provider, used, budget, budget - used])
    rows.append([])

    title("Weekly history (INR)")
    rows.append(["Week", "Leads", "People", "Contacts", "Content", "Total", "Leads added",
                 "Cost per lead", "Verified emails", "Cost per email", "Threads", "Cost per thread"])
    bold.append(len(rows))
    weeks = [("w", _week(now - timedelta(weeks=i))) for i in range(11, -1, -1)]
    active = [wk for wk in weeks if any(stage_inr(s, wk) for s in STAGES)
              or any(count(m, wk) for m in volume)]
    for wk in weeks[weeks.index(active[0]):] if active else []:   # from the first week with activity
        spent = {s: stage_inr(s, wk) for s in STAGES}
        leads_n, emails_n, threads_n = count("leads_added", wk), count("emails_verified", wk), count("threads_suggested", wk)
        rows.append([wk[1], *[inr(spent[s]) for s in STAGES], inr(sum(spent.values())), leads_n,
                     inr(spent["leads"] / leads_n) if leads_n else "-", emails_n,
                     inr(spent["contacts"] / emails_n) if emails_n else "-", threads_n,
                     inr(spent["content"] / threads_n) if threads_n else "-"])
    rows.append([])

    title("Totals in other currencies")
    rows.append(["", "INR", "USD", "EUR"]); bold.append(len(rows))
    for label, amount in [("Spent so far", total_so_far), ("This week", totals["This week"]),
                          ("This month", totals["This month"]), ("Last month", totals["Last month"])]:
        rows.append([label, inr(amount), round(amount / usd_inr, 2), round(amount / eur_inr, 2)])
    rows.append([f"Rates used: 1 USD = {usd_inr} INR, 1 EUR = {eur_inr} INR."])
    #--------------------------------------------------------------#

    ws = open_worksheet(sheets_cfg["spreadsheet_id"], sheets_cfg.get("costs_tab", "Costs"))
    ws.clear()
    ws.update(range_name="A1", values=rows, value_input_option="RAW")
    for r in bold:
        ws.format(f"A{r}:M{r}", {"textFormat": {"bold": True}})
    print(f"[{client}] costs: total spent so far INR {total_so_far:,.0f}; this month: ${totals['This month'] / usd_inr:.2f} / "
          f"EUR {totals['This month'] / eur_inr:.2f} / INR {totals['This month']:.0f}")
#--------------------------------------------------------------#
#---------------------end-of-code------------------------------#
