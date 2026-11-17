-- 014: email outreach (drafts, sends, replies) and the do-not-contact list
ALTER TABLE leads ADD COLUMN reach_out INTEGER DEFAULT 0;     -- Leads tab tick: draft an email for this lead
ALTER TABLE leads ADD COLUMN outreach_status TEXT;            -- shown in the Leads tab's "Outreach" column

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    lead_id INTEGER,
    kind TEXT,                  -- lead (hiring signal) or request (asked for help)
    company TEXT,
    to_email TEXT,
    to_name TEXT,
    signal TEXT,
    link TEXT,
    timezone TEXT,              -- recipient's, for working hours
    subject TEXT,               -- what was (or will be) sent, after your edits
    body TEXT,
    follow_up_body TEXT,
    draft_subject TEXT,         -- what the LLM wrote, to measure how much you changed
    draft_body TEXT,
    draft_follow_up TEXT,
    status TEXT,                -- drafted, approved, sent, followed_up, replied, bounced, skipped
    approved INTEGER DEFAULT 0,
    approved_at TEXT,
    sent_at TEXT,
    message_id TEXT,
    follow_up_sent_at TEXT,
    follow_up_message_id TEXT,
    replied_at TEXT,
    reply_label TEXT,
    reply_text TEXT,
    error TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (client_id, lead_id)
);

CREATE TABLE IF NOT EXISTS outreach_replies (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    outreach_id INTEGER,
    from_email TEXT,
    subject TEXT,
    body TEXT,
    label TEXT,                 -- interested, question, not_now, not_interested, unsubscribe, out_of_office, other, bounced
    summary TEXT,
    message_id TEXT UNIQUE,
    received_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS do_not_contact (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE,          -- never emailed again, by any client
    client_id INTEGER,
    reason TEXT,                -- unsubscribe, not_interested, bounced, manual
    added_at TEXT
);
