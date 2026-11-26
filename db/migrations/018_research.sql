-- 018: research notes (python3 -m job_alerts research)
-- Company updates from the last 3 months, read from public websites and matched to the client's
-- event rules (config: research.events). No LLM. Only for leads that already have an email.

-- Pages read on a company's website (shared by all clients: it's about the company)
CREATE TABLE IF NOT EXISTS research_pages (
  id INTEGER PRIMARY KEY,
  domain TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  source TEXT,                 -- feed, sitemap, news page
  title TEXT,
  published_at TEXT,           -- ISO date
  date_source TEXT,            -- meta, json-ld, time tag, url, text, feed, sitemap
  lang TEXT,
  text TEXT,                   -- the page's own text (lines repeated across the site removed), at most 6000 chars
  fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_pages_domain ON research_pages(domain);

-- What matched the client's rules: one row per lead, page and event
CREATE TABLE IF NOT EXISTS research_notes (
  id INTEGER PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  lead_id INTEGER NOT NULL REFERENCES leads(id),
  page_id INTEGER NOT NULL REFERENCES research_pages(id),
  event TEXT NOT NULL,         -- key from research.events
  points REAL,                 -- event points, lower the older the page
  matched TEXT,                -- the keywords that matched, comma separated
  snippet TEXT,                -- the sentence the first keyword is in
  created_at TEXT NOT NULL,
  UNIQUE (lead_id, page_id, event)
);
CREATE INDEX IF NOT EXISTS idx_research_notes_lead ON research_notes(lead_id);

-- One row per lead: when it was researched and when to look again
CREATE TABLE IF NOT EXISTS research_runs (
  lead_id INTEGER PRIMARY KEY REFERENCES leads(id),
  client_id INTEGER NOT NULL REFERENCES clients(id),
  status TEXT,                 -- ok, no updates, no website, unreachable, blocked
  pages_read INTEGER DEFAULT 0,
  notes INTEGER DEFAULT 0,
  ran_at TEXT,
  next_at TEXT
);
