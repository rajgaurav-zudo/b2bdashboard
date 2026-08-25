-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- Three columns the live export carries that the original spec did not name.
-- Added rather than ignored: re-projecting an archived upload to pick up a
-- column later is cheap, but only if the column was kept in the first place.

alter table logs add column if not exists log_id    text;   -- the CRM's own `_id`
alter table logs add column if not exists call_type text;   -- Inbound / Outbound, calls only
alter table logs add column if not exists outcome   text;   -- Connected / NoAnswer / Busy / WrongNumber

-- Outcome is the difference between contact attempted and contact made, so it
-- is worth an index of its own alongside the week.
create index if not exists logs_outcome on logs (load_id, outcome);
