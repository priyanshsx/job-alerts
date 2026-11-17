CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY, 
    name TEXT UNIQUE, 
    config_path TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    name TEXT,
    name_normalized TEXT,
    domain TEXT,
    linkedin_url TEXT,
    industry TEXT,
    company_type TEXT,
    country TEXT,
    employee_count INTEGER,
    erp_system TEXT,
    description TEXT,
    fit_score INTEGER,
    supplies_to TEXT,
    supplier_evidence_url TEXT,
    source TEXT,
    website TEXT,
    category TEXT,
    enriched_at TEXT,
    created_at TEXT,
    UNIQUE (client_id, name_normalized)
);

CREATE TABLE IF NOT EXISTS job_postings (
  id INTEGER PRIMARY KEY,
  client_id INTEGER,
  source TEXT,
  external_id TEXT,
  url TEXT,
  title TEXT,
  company_name TEXT,
  company_id INTEGER,
  location TEXT,
  country TEXT,
  posted_at TEXT,
  description TEXT,
  contact_name TEXT,
  is_relevant INTEGER,
  role_type TEXT,
  is_agency INTEGER,
  erp_system TEXT,
  segment TEXT,
  employer_type TEXT,
  reason TEXT,
  language_requirement TEXT,
  company_size TEXT,
  employee_estimate INTEGER,
  named_customers TEXT,
  supplies_anchor_customer INTEGER,
  supplier_evidence TEXT,
  priority INTEGER,
  business_model TEXT,
  vertical TEXT,
  classified_at TEXT,
  created_at TEXT,
  UNIQUE (client_id, source, external_id)
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    company_id INTEGER,
    person_id INTEGER,
    type TEXT,
    detail TEXT,
    source_url TEXT,
    points INTEGER,
    dedupe_key TEXT,
    detected_at TEXT,
    UNIQUE (client_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    job_posting_id INTEGER,
    sent_at TEXT,
    UNIQUE (client_id, job_posting_id)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    task TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TEXT   
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    task TEXT,
    response TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    full_name TEXT, 
    title TEXT, 
    company_name TEXT,
    location TEXT,
    linkedin_url TEXT,
    source TEXT,
    query TEXT,
    reason TEXT,
    priority INTEGER,
    status TEXT DEFAULT 'new',
    sent_at TEXT,
    connection_status TEXT,     -- from the People tab: to connect, requested, connected, conversation, skip
    note TEXT,
    last_updated TEXT,
    find_email INTEGER DEFAULT 0,
    email TEXT,
    email_status TEXT,
    email_source TEXT,
    email_checked_at TEXT,
    created_at TEXT,
    UNIQUE (client_id, linkedin_url)
);

CREATE TABLE IF NOT EXISTS people_searches (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    query TEXT,
    results INTEGER,
    run_at TEXT,
    UNIQUE (client_id, query)
);

CREATE TABLE IF NOT EXISTS supplier_searches (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    query TEXT,
    results INTEGER,
    run_at TEXT,
    UNIQUE (client_id, query)
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY, 
    client_id INTEGER,
    company_name TEXT,
    name_normalized TEXT,
    country TEXT,
    sources TEXT,
    latest_signal TEXT,
    latest_signal_at TEXT,
    priority INTEGER,
    language TEXT,
    company_size TEXT,
    links TEXT,
    on_team_list INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    owner TEXT,
    next_step TEXT,
    next_step_date TEXT,
    promising INTEGER DEFAULT 0,
    notes TEXT,
    last_updated TEXT,
    created_at TEXT,
    updated_at TEXT,
    find_contact INTEGER DEFAULT 0,
    contact_role TEXT,
    domain TEXT,
    contact_person_id INTEGER,
    contact_name TEXT,
    contact_title TEXT,
    contact_linkedin TEXT,
    contact_email TEXT,
    email_status TEXT,
    contact_checked_at TEXT,
    lead_type TEXT,
    request_id INTEGER,
    reach_out INTEGER DEFAULT 0,
    outreach_status TEXT,
    domain_status TEXT,
    domain_source TEXT,
    contact_source TEXT,
    email_source TEXT,
    email_method TEXT,
    extra_name TEXT,
    extra_title TEXT,
    extra_email TEXT,
    extra_email_status TEXT,
    enrich_attempts INTEGER DEFAULT 0,
    enrich_next_at TEXT,
    enriched_at TEXT,
    UNIQUE (client_id, name_normalized)
);

CREATE TABLE IF NOT EXISTS weekly_reviews_sent (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    week TEXT,
    sent_at TEXT,
    UNIQUE (client_id, week)
);

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

-- 009: job ads spotted in LinkedIn / SAP Community / Reddit posts (found by content-suggester)
-- that were turned into leads, so none is imported twice.
CREATE TABLE IF NOT EXISTS imported_hiring_posts (
  id INTEGER PRIMARY KEY,
  client_id INTEGER,
  item_id INTEGER,             -- the post's id in content-suggester's database
  lead_id INTEGER,
  created_at TEXT,
  UNIQUE (client_id, item_id)
);

-- 010: paid API calls other than the LLM (searches), for the cost dashboard.
CREATE TABLE IF NOT EXISTS api_calls (
  id INTEGER PRIMARY KEY,
  client_id INTEGER,
  service TEXT NOT NULL,          -- unoblox_search, serper
  task TEXT,                      -- the command that made the call (fetch, people-find, contacts, ...)
  units INTEGER NOT NULL DEFAULT 1,   -- what the service bills for (Unoblox: results; Serper: credits)
  cost_usd REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

-- 012: what we learn about company email domains (shared by all clients: it's about the company)
CREATE TABLE IF NOT EXISTS email_domains (
  domain TEXT PRIMARY KEY,
  pattern TEXT,                -- e.g. "first.last"; NULL = not learned yet
  pattern_source TEXT,         -- the verified email it was learned from
  mx_provider TEXT,            -- google, microsoft, proofpoint, mimecast, other, none
  catch_all INTEGER DEFAULT 0, -- 1 = the domain accepts every address: guesses can't be verified
  checked_at TEXT
);

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    lead_id INTEGER,
    kind TEXT,                  -- lead (hiring signal) or request (asked for help)
    company TEXT,
    to_email TEXT,
    to_name TEXT,
    signal TEXT,
    link TEXT,
    timezone TEXT,              -- recipient's, for working hours
    subject TEXT,               -- what was (or will be) sent, after your edits
    body TEXT,
    follow_up_body TEXT,
    draft_subject TEXT,         -- what the LLM wrote, to measure how much you changed
    draft_body TEXT,
    draft_follow_up TEXT,
    status TEXT,                -- drafted, approved, sent, followed_up, replied, bounced, skipped
    approved INTEGER DEFAULT 0,
    approved_at TEXT,
    sent_at TEXT,
    message_id TEXT,
    follow_up_sent_at TEXT,
    follow_up_message_id TEXT,
    replied_at TEXT,
    alerted_at TEXT,
    follow_up_alerted_at TEXT,
    reply_label TEXT,
    reply_text TEXT,
    error TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (client_id, lead_id)
);

CREATE TABLE IF NOT EXISTS outreach_replies (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    outreach_id INTEGER,
    from_email TEXT,
    subject TEXT,
    body TEXT,
    label TEXT,                 -- interested, question, not_now, not_interested, unsubscribe, out_of_office, other, bounced
    summary TEXT,
    message_id TEXT UNIQUE,
    received_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS do_not_contact (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE,          -- never emailed again, by any client
    client_id INTEGER,
    reason TEXT,                -- unsubscribe, not_interested, bounced, manual
    added_at TEXT
);

CREATE TABLE IF NOT EXISTS outreach_alerts (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    slot TEXT,                  -- e.g. "2026-11-18 09:00" (alert time zone)
    items TEXT,                 -- outreach ids in the alert
    sent_at TEXT,
    UNIQUE (client_id, slot)
);

-- 016: enrichment crawler
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
