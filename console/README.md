# Console

The internal app for the Vizcorn team. It reads the same database the terminal commands write
(`data/job_alerts.db`, plus content-suggester's database for Engage). It only shows the clients
in `config/console.yaml`.

## One-time setup
    pip install -e ".[console]"
    sqlite3 data/job_alerts.db < db/migrations/017_console.sql
    sqlite3 data/job_alerts.db < db/migrations/018_research.sql
    sqlite3 data/job_alerts.db < db/migrations/019_console_dates.sql

## Running it
    python3 -m streamlit run console/app.py      # opens http://localhost:8501

The Google Sheet is off for Vizcorn (sheets.enabled: false). New leads from the fetch commands
show up in the console directly. scripts/import_sheet.py still reads the old sheet if ever needed.

## The flow
1. Raw leads: paste the person's name and LinkedIn profile on the lead's page, check the company name.
2. Run enrichment (one lead, or "Enrich N with a contact" on the board): website, email, research notes.
3. Log the first email with its date. Follow-up 1 is due 7 days later, follow-up 2 five days after that,
   then a check-in 25 days after the last email (config/console.yaml, follow_ups).

## Who writes what
- The engine's commands write leads, people, emails and costs (same as before).
- The console's buttons (Mark as sent, Follow-up sent, Log a reply, Not a fit, Engage done/skip)
  go to `lead_events` and `engage_actions`. A sheet sync never touches those.
- `sheet_rows` is a copy of the Google Sheet, so hand-added columns show on each lead's page.
