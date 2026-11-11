-- 008: who a hiring company sells to (b2b, b2c, both, unknown), for non-SAP clients like Bacon
ALTER TABLE job_postings ADD COLUMN business_model TEXT;
