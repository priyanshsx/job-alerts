-- 015: manual outreach mode (alerts instead of sending, e.g. Vizcorn)
ALTER TABLE outreach ADD COLUMN alerted_at TEXT;             -- first email included in an alert
ALTER TABLE outreach ADD COLUMN follow_up_alerted_at TEXT;   -- follow-up included in an alert

CREATE TABLE IF NOT EXISTS outreach_alerts (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    slot TEXT,                  -- e.g. "2026-11-18 09:00" (alert time zone)
    items TEXT,                 -- outreach ids in the alert
    sent_at TEXT,
    UNIQUE (client_id, slot)
);
