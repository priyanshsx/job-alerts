-- 016: the enrichment crawler (python3 -m job_alerts enrich)
-- Finds each lead's domain and email from public company websites, verifies with MillionVerifier.

-- Leads: what the crawler found, and when to look again
ALTER TABLE leads ADD COLUMN domain_status TEXT;      -- confirmed, manual, uncertain, not_found
ALTER TABLE leads ADD COLUMN domain_source TEXT;      -- how it was found: job link, job text, job page, guess, search, manual
ALTER TABLE leads ADD COLUMN contact_source TEXT;     -- linkedin (contacts command / Manual Lookup) or website (crawler)
ALTER TABLE leads ADD COLUMN email_source TEXT;       -- URL where the email or its format was seen
ALTER TABLE leads ADD COLUMN email_method TEXT;       -- found on site, company format, common format
ALTER TABLE leads ADD COLUMN extra_name TEXT;         -- a second person from the website (e.g. managing director)
ALTER TABLE leads ADD COLUMN extra_title TEXT;
ALTER TABLE leads ADD COLUMN extra_email TEXT;
ALTER TABLE leads ADD COLUMN extra_email_status TEXT;
ALTER TABLE leads ADD COLUMN enrich_attempts INTEGER DEFAULT 0;
ALTER TABLE leads ADD COLUMN enrich_next_at TEXT;     -- NULL = due now; 9999 = finished
ALTER TABLE leads ADD COLUMN enriched_at TEXT;

-- One row per website crawled (shared by all clients: it's about the company)
CREATE TABLE IF NOT EXISTS site_crawls (
  domain TEXT PRIMARY KEY,
  home_url TEXT,               -- where the site really lives after redirects
  pages INTEGER DEFAULT 0,
  emails_found INTEGER DEFAULT 0,
  people TEXT,                 -- JSON: named people seen on the site (name, role, source_url)
  status TEXT,                 -- ok, unreachable, blocked
  crawled_at TEXT
);

-- Every email address seen on a public page, with where it was seen (GDPR: source recorded)
CREATE TABLE IF NOT EXISTS site_emails (
  id INTEGER PRIMARY KEY,
  domain TEXT,                 -- the website it was found on
  email TEXT,
  name TEXT,                   -- the person's name next to it, only when the address matches the name
  email_format TEXT,           -- e.g. first.last (when a name matched)
  is_generic INTEGER DEFAULT 0,-- info@, sales@, jobs@ ...
  source_url TEXT,
  found_at TEXT,
  UNIQUE (domain, email)
);

-- MillionVerifier answers, so no address is ever paid for twice (shared by all clients)
CREATE TABLE IF NOT EXISTS email_verifications (
  email TEXT PRIMARY KEY,
  status TEXT,                 -- verified, catch_all, invalid, unknown, error
  detail TEXT,
  checked_at TEXT
);
