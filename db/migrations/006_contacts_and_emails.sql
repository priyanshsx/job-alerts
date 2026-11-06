-- Leads: Monday ticks from the sheet, and the contact found for each ticked lead
ALTER TABLE leads ADD COLUMN find_contact INTEGER DEFAULT 0;
ALTER TABLE leads ADD COLUMN contact_role TEXT;
ALTER TABLE leads ADD COLUMN domain TEXT;
ALTER TABLE leads ADD COLUMN contact_person_id INTEGER;
ALTER TABLE leads ADD COLUMN contact_name TEXT;
ALTER TABLE leads ADD COLUMN contact_title TEXT;
ALTER TABLE leads ADD COLUMN contact_linkedin TEXT;
ALTER TABLE leads ADD COLUMN contact_email TEXT;
ALTER TABLE leads ADD COLUMN email_status TEXT;
ALTER TABLE leads ADD COLUMN contact_checked_at TEXT;

-- People: Monday ticks, and the email found
ALTER TABLE people ADD COLUMN find_email INTEGER DEFAULT 0;
ALTER TABLE people ADD COLUMN email TEXT;
ALTER TABLE people ADD COLUMN email_status TEXT;      -- verified, risky, not_found
ALTER TABLE people ADD COLUMN email_source TEXT;      -- apollo, prospeo, hunter
ALTER TABLE people ADD COLUMN email_checked_at TEXT;

-- Company domains, found once and reused
CREATE TABLE IF NOT EXISTS company_domains (
  id INTEGER PRIMARY KEY,
  client_id INTEGER,
  name_normalized TEXT,
  domain TEXT,                 -- empty string = searched, none found
  source_url TEXT,
  checked_at TEXT,
  UNIQUE (client_id, name_normalized)
);

-- Every email lookup attempt, for credit tracking and never repeating a lookup
CREATE TABLE IF NOT EXISTS email_lookups (
  id INTEGER PRIMARY KEY,
  client_id INTEGER,
  person_id INTEGER,
  provider TEXT,
  result TEXT,                 -- found, not_found, error
  email TEXT,
  email_status TEXT,
  credits INTEGER DEFAULT 0,
  detail TEXT,
  created_at TEXT
);
