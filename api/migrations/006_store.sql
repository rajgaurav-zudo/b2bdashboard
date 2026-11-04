-- The store: one table per source holding the latest upload's rows exactly as
-- uploaded, and the changelog of what each upload changed.
--
-- Dashboards used to keep every load they were ever given, so a 237k-row
-- export landed in four tables per upload and stayed there: 27 loads deep in
-- Introducer performance alone. Now the raw rows live once, here, replaced on
-- every upload; a dashboard keeps only the load it is serving, and the history
-- of what moved is the changelog below rather than old copies of the data.
--
-- The per-source row tables (store.applications, ...) are created by the
-- ingest on first use, so a source added to sources.yaml needs no migration.

create schema if not exists store;

-- Which upload each store table currently holds, and the header it came with:
-- the rows keep their values positionally, so the column names live here once.
create table if not exists store.snapshots (
  source_id   bigint primary key references core.sources(id) on delete cascade,
  upload_id   bigint not null references core.uploads(id) on delete cascade,
  columns     text[] not null,
  key_column  text,
  row_count   integer not null,
  loaded_at   timestamptz not null default now()
);

-- The changelog moves into the store with its history intact. Entries written
-- before this migration are per dashboard (dashboard_id set); entries from now
-- on are per source (source_id set, dashboard_id null) because the diff is of
-- the file, not of what one dashboard made of it.
do $$
begin
  if to_regclass('core.changelog') is not null and to_regclass('store.changelog') is null then
    alter table core.changelog set schema store;
    alter table core.changelog_rows set schema store;
    alter sequence if exists core.changelog_id_seq set schema store;
    alter sequence if exists core.changelog_rows_id_seq set schema store;
  end if;
end $$;

alter table store.changelog alter column dashboard_id drop not null;
alter table store.changelog add column if not exists source_id bigint references core.sources(id) on delete cascade;
alter table store.changelog add column if not exists previous_upload_id bigint references core.uploads(id) on delete set null;

update store.changelog c set source_id = u.source_id
  from core.uploads u
 where u.id = c.upload_id and c.source_id is null;

create index if not exists changelog_source_feed on store.changelog (source_id, occurred_at desc);

-- A load whose rows were deleted when the next one went current. The row stays
-- as the record of what was loaded, from which file, and with what stats.
alter table core.loads add column if not exists purged_at timestamptz;
