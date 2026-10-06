-- The CRM's own log id, kept beside log_uid so the side pane can show it.
alter table logs add column if not exists log_id text;
