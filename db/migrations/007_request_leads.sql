-- 007: leads created from the Requests tab (people asking for help in public)
ALTER TABLE leads ADD COLUMN request_id INTEGER;     -- the Request ID it came from (never imported twice)
