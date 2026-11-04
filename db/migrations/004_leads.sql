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
    UNIQUE (client_id, name_normalized)
);

CREATE TABLE IF NOT EXISTS weekly_reviews_sent (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    week TEXT,
    sent_at TEXT,
    UNIQUE (client_id, week)
);