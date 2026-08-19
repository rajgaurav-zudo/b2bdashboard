-- Ingest-time counts that cannot be recovered from the loaded rows: how many
-- input rows were collapsed or dropped on the way in. Each dashboard decides
-- what to put here via an optional stats() hook in its ingest module.
alter table core.loads add column if not exists stats jsonb not null default '{}'::jsonb;
