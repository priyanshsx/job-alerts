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
    priority INTEGER,
    classified_at TEXT,
    created_at TEXT,
    employer_type TEXT, 
    reason TEXT,
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
