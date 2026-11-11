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
    request_id INTEGER,
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
