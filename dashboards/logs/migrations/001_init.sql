-- Runs with search_path set to this dashboard's schema. Unqualified names only.

create table if not exists logs (
  load_id         bigint not null references core.loads(id) on delete cascade,
  log_uid         text   not null,
  -- the log's date, time of day discarded. Rows whose Log Time cannot be read
  -- never reach this table; the count of them is recorded on the load's stats.
  logged_on       date   not null,
  -- Saturday of the week this log falls in. Stored rather than derived so every
  -- query buckets identically and the index is usable.
  week_start      date   not null,
  log_type        text,
  introducer_name text,
  managed_by_team text,
  created_by      text,
  note            text,
  note_words      int     not null default 0,
  -- keyword-lexicon sentiment, -1..+1. NULL means no lexicon term matched:
  -- an unscored note is neutral, not missing. See ingest.py for the lexicon.
  note_score      real,
  note_hits       int     not null default 0,
  row_hash        bigint  not null,
  primary key (load_id, log_uid)
);
create index if not exists logs_week on logs (load_id, week_start);
create index if not exists logs_week_type on logs (load_id, week_start, log_type);
create index if not exists logs_introducer on logs (load_id, introducer_name);
create index if not exists logs_team on logs (load_id, managed_by_team);
create index if not exists logs_creator on logs (load_id, created_by);
