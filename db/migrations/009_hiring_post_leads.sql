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
