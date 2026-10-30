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
