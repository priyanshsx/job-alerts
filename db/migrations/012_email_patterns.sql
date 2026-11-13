-- 012: what we learn about company email domains (shared by all clients: it's about the company)
CREATE TABLE IF NOT EXISTS email_domains (
  domain TEXT PRIMARY KEY,
  pattern TEXT,                -- e.g. "first.last"; NULL = not learned yet
  pattern_source TEXT,         -- the verified email it was learned from
  mx_provider TEXT,            -- google, microsoft, proofpoint, mimecast, other, none
  catch_all INTEGER DEFAULT 0, -- 1 = the domain accepts every address: guesses can't be verified
  checked_at TEXT
);
