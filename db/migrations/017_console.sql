-- 017: the internal console (streamlit run console/app.py)
-- The console never changes the engine's own columns. It keeps what the team does in its own tables,
-- so a sheet sync can't overwrite it.

-- What the team logged on a lead: sent, follow_up, replied, not_fit, reopened
CREATE TABLE IF NOT EXISTS lead_events (
  id INTEGER PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  lead_id INTEGER NOT NULL REFERENCES leads(id),
  event TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lead_events_lead ON lead_events(lead_id);

-- Posts the team engaged with or skipped (item ids from content-suggester's database)
CREATE TABLE IF NOT EXISTS engage_actions (
  id INTEGER PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  item_id INTEGER NOT NULL,
  action TEXT NOT NULL,            -- done, skipped
  created_at TEXT NOT NULL,
  UNIQUE (client_id, item_id)
);

-- A copy of every row of every tab of the client's Google Sheet (scripts/import_sheet.py),
-- so columns the team added by hand are kept too
CREATE TABLE IF NOT EXISTS sheet_rows (
  id INTEGER PRIMARY KEY,
  spreadsheet_id TEXT NOT NULL,
  tab TEXT NOT NULL,
  row_number INTEGER NOT NULL,
  row_key TEXT,                    -- Lead ID or Person ID when the tab has one
  cells TEXT NOT NULL,             -- JSON: {header: value}, empty cells left out
  imported_at TEXT NOT NULL,
  UNIQUE (spreadsheet_id, tab, row_number)
);
CREATE INDEX IF NOT EXISTS idx_sheet_rows_key ON sheet_rows(tab, row_key);
