-- 019: the date something really happened (e.g. the email went out yesterday, logged today)
ALTER TABLE lead_events ADD COLUMN happened_on TEXT;     -- ISO date; NULL = the day it was logged
