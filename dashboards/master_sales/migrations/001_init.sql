-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- One row per application, every recruitment type. `stage` is the furthest
-- stage on the ladder Applied -> Enrolled this application has reached as the
-- export stands; the `on_*` dates are when it first reached each, backfilled
-- from later stages. Deposit is not on the ladder: it can be paid at any point
-- from Offered on, so it has its own flag and date. See context.md.

create table if not exists applications (
  load_id           bigint not null references core.loads(id) on delete cascade,
  app_uid           text   not null,
  application_id    text,
  student_key       text   not null,     -- Student Ref Id, or the app when it has none

  business_area     text   not null default 'Unassigned',
  business_region   text   not null default 'Unassigned',
  business_team     text   not null default 'Unassigned',

  application_status  text,
  deposit_paid_status text,
  closed_lost       boolean not null default false,

  intake_year       int,
  intake_month      smallint,             -- 1..12

  -- 0 none · 1 Applied · 2 Offered · 3 CoE · 4 Visa applied · 5 Visa granted · 6 Enrolled
  stage             smallint not null default 0,
  on_applied        date,
  on_offered        date,
  on_coe            date,
  on_visa_applied   date,
  on_visa_granted   date,
  on_enrolled       date,

  deposit           boolean not null default false,
  on_deposit        date,

  row_hash          bigint not null,
  primary key (load_id, app_uid)
);

create index if not exists apps_load on applications (load_id, intake_year, intake_month);
