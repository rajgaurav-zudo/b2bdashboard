-- Uploads become platform-level.
--
-- Until now an upload belonged to one dashboard, so a second dashboard needing
-- the same applications export meant uploading the same 114MB file again, into
-- a second archive, with a second sha to keep straight. The file is not the
-- dashboard's; it is the CRM's. What belongs to a dashboard is what it takes
-- out of that file.
--
--   core.sources      a kind of file the platform accepts, once
--   core.uploads      one file that arrived, belonging to a source
--   core.projections  one dashboard's attempt to read that file into its tables
--   core.loads        the snapshot a successful projection produced (unchanged)
--
-- Isolation is unchanged, and is the reason projections are rows rather than a
-- status on the upload: one upload now has N outcomes, and dashboard B failing
-- to project must leave dashboard A's load exactly as it was.

create table if not exists core.sources (
  id            bigserial primary key,
  slug          text unique not null,
  display_name  text not null,
  description   text,
  -- normalised header fragments that must all be present for a file to be this
  -- source. The upload endpoint no longer has a dashboard to ask, so the source
  -- is what knows whether the right file arrived.
  identified_by text[] not null default '{}',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Which source feeds a dataset. Nullable only until the backfill below fills it.
alter table core.datasets add column if not exists source_id bigint references core.sources(id);

alter table core.uploads add column if not exists source_id bigint references core.sources(id);

-- --- backfill -----------------------------------------------------------------
-- Existing datasets are named after the file that feeds them ('introducers',
-- 'applications'), which is exactly the mapping being made explicit.
insert into core.sources (slug, display_name)
select distinct ds.slug, ds.display_name
  from core.datasets ds
on conflict (slug) do nothing;

update core.datasets ds
   set source_id = s.id
  from core.sources s
 where s.slug = ds.slug and ds.source_id is null;

update core.uploads u
   set source_id = ds.source_id
  from core.datasets ds
 where ds.id = u.dataset_id and u.source_id is null;

create table if not exists core.projections (
  id           bigserial primary key,
  upload_id    bigint not null references core.uploads(id)     on delete cascade,
  dashboard_id bigint not null references core.dashboards(id)  on delete cascade,
  dataset_id   bigint not null references core.datasets(id)    on delete cascade,
  load_id      bigint references core.loads(id)                on delete set null,
  row_count    int,
  status       text not null default 'pending'
               check (status in ('pending','loading','diffing','ready','failed','duplicate')),
  error        text,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  -- one attempt per dashboard-dataset per file; re-projecting updates it
  unique (upload_id, dataset_id)
);
create index if not exists projections_by_dashboard
  on core.projections (dashboard_id, started_at desc);

-- Every upload so far was one dashboard reading one file, which is a projection
-- with the numbers already known. Reconstructed rather than discarded, so the
-- Data tab keeps showing the history it showed yesterday.
insert into core.projections
  (upload_id, dashboard_id, dataset_id, load_id, row_count, status, error, started_at, finished_at)
select u.id, u.dashboard_id, u.dataset_id, l.id, u.row_count,
       case when u.status in ('ready','failed','duplicate') then u.status else 'failed' end,
       u.error, u.started_at, u.finished_at
  from core.uploads u
  left join core.loads l on l.upload_id = u.id
 where u.dashboard_id is not null and u.dataset_id is not null
on conflict (upload_id, dataset_id) do nothing;

-- Refuse to go further if anything was left behind. A migration that silently
-- half-converts an audit trail is worse than one that stops.
do $$
declare orphans int;
begin
  select count(*) into orphans from core.uploads where source_id is null;
  if orphans > 0 then
    raise exception 'backfill incomplete: % upload(s) without a source', orphans;
  end if;
  select count(*) into orphans from core.datasets where source_id is null;
  if orphans > 0 then
    raise exception 'backfill incomplete: % dataset(s) without a source', orphans;
  end if;
end $$;

alter table core.uploads alter column source_id set not null;

-- The upload no longer belongs to a dashboard; core.projections says who read it.
-- Dropped rather than left nullable: a column that is sometimes right is how a
-- wrong answer gets served later.
alter table core.uploads drop column if exists dashboard_id;
alter table core.uploads drop column if exists dataset_id;

-- One archived file per source, so re-uploading the same export is recognised
-- however many dashboards happen to read it.
create index if not exists uploads_by_source on core.uploads (source_id, started_at desc);
create index if not exists uploads_by_sha on core.uploads (source_id, sha256);
