-- 011: what kind of lead a company is for the client (e.g. "Partner (MSSP / SI)" or "Direct client")
ALTER TABLE leads ADD COLUMN lead_type TEXT;
