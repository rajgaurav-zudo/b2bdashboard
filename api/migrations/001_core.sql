-- Core registry: dashboards, their datasets, every upload, every load, the changelog.
-- Dashboard *data* never lives here; each dashboard owns its own schema.

create schema if not exists core;

create table if not exists core.schema_migrations (
  scope      text not null,                 -- 'core', or a dashboard slug
  version    text not null,
  applied_at timestamptz not null default now(),
  primary key (scope, version)
);

create table if not exists core.dashboards (
  id          bigserial primary key,
  slug        text unique not null,
  name        text not null,
  version     int  not null default 1,
  db_schema   text not null,
  context_sha text,                          -- sha256 of context.md: spec changes are visible
  manifest    jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists core.datasets (
  id               bigserial primary key,
  dashboard_id     bigint not null references core.dashboards(id) on delete cascade,
  slug             text not null,
  display_name     text not null,
  table_name       text not null,
  natural_key      text[] not null,
  required_columns text[] not null default '{}',
  unique (dashboard_id, slug)
);

create table if not exists core.uploads (
  id           bigserial primary key,
  dashboard_id bigint not null references core.dashboards(id) on delete cascade,
  dataset_id   bigint not null references core.datasets(id)   on delete cascade,
  filename     text   not null,
  byte_size    bigint not null,
  sha256       text   not null,
  stored_path  text,
  row_count    int,
  status       text   not null default 'pending'
               check (status in ('pending','parsing','loading','diffing','ready','failed','duplicate')),
  error        text,
  uploaded_by  text,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz
);
create index if not exists uploads_recent on core.uploads (dashboard_id, dataset_id, started_at desc);

-- Every load is kept: a load is one snapshot of one dataset, addressable forever.
create table if not exists core.loads (
  id            bigserial primary key,
  dashboard_id  bigint not null references core.dashboards(id) on delete cascade,
  dataset_id    bigint not null references core.datasets(id)   on delete cascade,
  upload_id     bigint not null references core.uploads(id)    on delete cascade,
  row_count     int not null default 0,
  is_current    boolean not null default false,
  created_at    timestamptz not null default now(),
  superseded_at timestamptz
);
create unique index if not exists loads_one_current
  on core.loads (dashboard_id, dataset_id) where is_current;

-- One row per (upload, entity): the human-readable feed.
create table if not exists core.changelog (
  id               bigserial primary key,
  dashboard_id     bigint not null references core.dashboards(id) on delete cascade,
  dataset_id       bigint references core.datasets(id) on delete cascade,
  upload_id        bigint references core.uploads(id)  on delete cascade,
  load_id          bigint references core.loads(id)    on delete set null,
  previous_load_id bigint references core.loads(id)    on delete set null,
  entity           text not null,
  rows_added       int not null default 0,
  rows_removed     int not null default 0,
  rows_changed     int not null default 0,
  rows_unchanged   int not null default 0,
  rows_sampled     int not null default 0,   -- how many row-level diffs were stored
  summary          text not null,
  details          jsonb not null default '{}'::jsonb,
  occurred_at      timestamptz not null default now()
);
create index if not exists changelog_feed on core.changelog (dashboard_id, occurred_at desc);

-- Row-level diffs, hanging off a changelog entry.
create table if not exists core.changelog_rows (
  id             bigserial primary key,
  changelog_id   bigint not null references core.changelog(id) on delete cascade,
  change_type    text not null check (change_type in ('added','removed','changed')),
  natural_key    text not null,
  changed_fields text[] not null default '{}',
  before         jsonb,
  after          jsonb
);
create index if not exists changelog_rows_lookup on core.changelog_rows (changelog_id, change_type);
