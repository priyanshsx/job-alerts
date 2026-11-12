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
