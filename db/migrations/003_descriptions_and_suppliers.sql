ALTER TABLE job_postings ADD COLUMN language_requirement TEXT;
ALTER TABLE job_postings ADD COLUMN company_size TEXT;
ALTER TABLE job_postings ADD COLUMN employee_estimate INTEGER;
ALTER TABLE job_postings ADD COLUMN named_customers TEXT;
ALTER TABLE job_postings ADD COLUMN supplies_anchor_customer INTEGER;
ALTER TABLE job_postings ADD COLUMN supplier_evidence TEXT;

ALTER TABLE companies ADD COLUMN supplies_to TEXT;
ALTER TABLE companies ADD COLUMN supplier_evidence_url TEXT;
ALTER TABLE companies ADD COLUMN source TEXT;
ALTER TABLE companies ADD COLUMN website TEXT;
ALTER TABLE companies ADD COLUMN category TEXT;

CREATE TABLE IF NOT EXISTS supplier_searches (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    query TEXT,
    results INTEGER,
    run_at TEXT,
    UNIQUE (client_id, query)
);