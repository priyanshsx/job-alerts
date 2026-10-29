# Job Alerts

**A daily email of companies that are hiring for the problem you solve.**

When a company posts a job for a master data specialist, a data governance lead or an ERP project manager, it is telling the market it has a problem right now. Job Alerts watches job boards every morning, filters out the noise, uses an LLM to judge each posting against your ideal customer profile, and emails you a short, ranked list of companies worth contacting, with one-click links to find the right people.

It is built for B2B service firms and consultancies doing signal-based outreach, and is configured per client with a single YAML file.

---

## What you get

Every morning, an email grouped into three sections:

- **Target customers:** companies in your target segment hiring for a project or leadership role (the strongest signals)
- **Worth a look:** good-fit companies with ongoing needs, and companies outside the core segment with a clear project
- **Partner leads:** consultancies and integrators hiring in your field, a sign they have more work than people (subcontracting opportunities)

Each entry looks like this:

> **Teamleitung Stammdatenmanagement in SAP S/4HANA (m/w/d)**
> Example Fertigung GmbH · Bielefeld · posted 2026-10-27
> Manufacturer / supplier · lead role · SAP
> Job posting · LinkedIn: Head of IT · LinkedIn: master data · Company

The LinkedIn links open a people search for the right roles at that company, so finding a contact takes one click. Nothing is ever sent twice, and a copy of each digest is saved as an HTML file.

## How it works

```
fetch  →  filter  →  classify  →  prioritize  →  digest
```

1. **Fetch:** pulls postings from the last few days for each keyword in the client's config (currently Germany's Federal Employment Agency job search, covering Germany, with some Austria and Switzerland listings).
2. **Filter:** keeps only postings whose **title** contains a relevant term, drops excluded terms (internships, unrelated meanings) and known staffing agencies, and removes duplicates across keywords and days.
3. **Classify:** an LLM labels each new posting: is it relevant, what type of employer (manufacturer/supplier, consultancy, large enterprise, other industry, agency), what type of role (project, lead, routine) and which ERP system. Answers are validated against a fixed schema, so labels are always clean.
4. **Prioritize:** rules in the client's config turn those labels into priority 1, 2 or 3. Changing focus is a config edit, not a code change or a paid re-run.
5. **Digest:** priorities 1 and 2 go into the email; the rest stay in the database for later.

In a first run for a data quality consultancy, this went from **1,610 raw postings to 149 relevant ones, and from there to 48 worth emailing**, including 4 top-priority leads.

## Design principles

- **One codebase, many clients.** Everything client-specific lives in `config/clients/<client>/config.yaml`.
- **The LLM labels facts; the config decides priority.** Keeps results explainable and cheap to adjust.
- **Pay once per posting.** Every LLM answer is cached, and only new postings are classified.
- **Humans do the outreach.** The tool finds and ranks; people decide who to contact and write to them. No LinkedIn scraping or automation.
- **Every cost is logged** per client and per task.

## Tech stack

Python 3.11+, SQLite, Pydantic, PyYAML, httpx, the OpenAI-compatible SDK (via an LLM gateway; any OpenAI-compatible endpoint works), and SMTP for email.

## Project structure

```
job-alerts/
├── config/
│   ├── templates/b2b.yaml           # defaults for every B2B client
│   └── clients/<client>/config.yaml # one file per client (kept out of git)
├── db/
│   ├── schema.sql
│   └── migrations/
├── job_alerts/
│   ├── core/          # config loader, database, LLM helper
│   ├── sources/       # job board connectors
│   ├── collect.py     # fetch + filter + store
│   ├── classify.py    # LLM classification
│   ├── prioritize.py  # config-driven priority rules
│   ├── digest.py      # build and send the email
│   └── cli.py
├── scripts/           # init_db.py, new_client.py
├── data/              # database and cache (gitignored)
└── outputs/           # saved digests (gitignored)
```

## Setup

```bash
git clone <repo-url> job-alerts && cd job-alerts
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create a `.env` file in the repo root:

```dotenv
UNOBLOX_API_KEY=your-gateway-key
LLM_MODEL=anthropic/claude-sonnet-5-5
LLM_PRICE_INPUT_PER_MTOK=199.89
LLM_PRICE_OUTPUT_PER_MTOK=999.42

SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=alerts@example.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=alerts@example.com
```

Prices are per million tokens, in the gateway's billing currency. For Gmail, use an app password (Google Account → Security → 2-Step Verification → App passwords).

Create the database and register a client:

```bash
python scripts/init_db.py
python scripts/new_client.py acme
```

Then fill in `config/clients/acme/config.yaml` (see `config/clients/example/` for a complete example).

## Configuring a client

The parts of the config this tool uses:

```yaml
client: acme
display_name: Acme Data Services
offer: >
  What the client sells, in one or two sentences.
positioning: >
  Who the client is and who it serves.

segments:            # who the client targets; used by the classifier
  - name: supplier
    description: Mid-sized manufacturers and suppliers
    priority: 1
    industries: {automotive: 30, fmcg: 25}
    company_size: {min: 50, max: 2000, points: 20}
    titles: [...]

listening:
  job_keywords: [master data, Stammdaten, data quality, MDM]
  job_title_must_contain: [stammdaten, master data, data quality, data governance]
  job_exclude_keywords: [Werkstudent, Praktikum, mobile device]
  job_agency_names: [hays, randstad, staffing, recruitment]
  job_countries: [DE, AT, CH]

job_alerts:
  digest_max_priority: 2
  priority_rules:    # first matching rule wins
    - {employer_types: [manufacturer_supplier], role_types: [project, lead], priority: 1}
    - {employer_types: [manufacturer_supplier], role_types: [routine, other], priority: 2}
    - {employer_types: [other_industry, unknown], role_types: [project, lead], priority: 2}
    - {employer_types: [consultancy], role_types: [project, lead, routine, other], priority: 2}
    - {employer_types: [other_industry, unknown, large_enterprise], role_types: [project, lead, routine, other], priority: 3}

digest:
  email_to: ["team@example.com"]
  max_items: 50
```

The loader merges this with `config/templates/b2b.yaml` and validates every field, so a missing or misspelled required field fails with a clear error before anything runs.

## Commands

Run from the repo root (the folder with `pyproject.toml`):

| Command | What it does |
|---|---|
| `python -m job_alerts fetch --client acme` | Fetch and store new postings |
| `python -m job_alerts classify --client acme` | Classify new postings with the LLM |
| `python -m job_alerts prioritize --client acme` | Apply the priority rules from the config |
| `python -m job_alerts digest --client acme --dry-run` | Build the digest and save it as HTML, without sending |
| `python -m job_alerts digest --client acme` | Send the digest |
| `python -m job_alerts run --client acme` | All of the above, in order |

## Running it every morning

On macOS or Linux, add a cron job (`crontab -e`):

```
0 8 * * * cd /path/to/job-alerts && .venv/bin/python -m job_alerts run --client acme >> data/cron.log 2>&1
```

Cron only runs while the machine is awake; for guaranteed daily runs, move it to a small server or a scheduled CI job.

## Cost

With a mid-sized model, classifying one posting costs about ₹0.28 (roughly 800 input and 120 output tokens). A first run of around 150 postings costs about ₹40; a normal day with 20–50 new postings costs ₹6–14, or roughly ₹300 a month per client. The job source is free.

Check logged costs at any time:

```bash
python -c "from job_alerts.core.db import get_conn; print(get_conn().execute('SELECT task, COUNT(*), SUM(cost_usd) FROM llm_calls GROUP BY task').fetchall())"
```

## Limitations and notes

- **The job source is not an official API.** Germany's Federal Employment Agency doesn't publish an official API; the connector uses the interface behind its job search website, documented by the community project [bundesAPI](https://github.com/bundesAPI/jobsuche-api). It may change without notice, and requests are paced to stay polite.
- **Classification uses title and company name only.** Small companies the model doesn't recognize are labelled "unknown"; adding company lookups or full job descriptions is on the roadmap.
- **Title filtering trades recall for precision.** Postings with generic titles (e.g. "SAP Consultant") whose relevance is only in the description are missed.
- **Outreach rules vary by country.** In Germany, cold email for marketing generally requires prior consent, including B2B. Check local rules before contacting anyone; LinkedIn is usually the safer first channel.
- **Personal data:** the tool stores company and posting data, plus contact names only where a posting includes them. Treat the database accordingly (GDPR applies to EU data).

## Roadmap

- More sources: an EU-wide job aggregator, company careers pages
- Company lookups for unrecognized employers (industry, size, website)
- Full job descriptions for postings with generic titles
- Warm-path checks: flag companies where your team already has LinkedIn connections
- Integration into a wider GTM engine (people finder, market intelligence, content)