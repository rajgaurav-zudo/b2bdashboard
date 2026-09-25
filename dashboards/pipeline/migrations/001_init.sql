-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- One row per application, every recruitment type. The page never counts rows:
-- it rolls them up to students (`student_key`) inside an intake scope and keeps
-- each student's furthest stage. `stage` is that furthest stage for this one
-- application as the export stands; the `on_*` dates are when it first reached
-- each stage, backfilled from later stages (an application with a visa date had
-- reached Offer no later than that), which is what "the same point last year"
-- is read from. See context.md.

create table if not exists applications (
  load_id           bigint not null references core.loads(id) on delete cascade,
  app_uid           text   not null,
  application_id    text,
  student_key       text   not null,     -- Student Ref Id, or the app when it has none
  recruitment_type  text,
  course_level      text   not null default 'Unspecified',
  application_status text,
  deposit_paid_status text,
  closed_lost       boolean not null default false,

  intake_year       int,
  intake_month      smallint,             -- 1..12
  intake_ym         int,                  -- year * 100 + month, what a scope filters on

  -- 0 none · 1 Applied · 2 Offer · 3 Deposit · 4 CoE · 5 Visa granted · 6 Enrolled
  stage             smallint not null default 0,
  on_applied        date,
  on_offer          date,
  on_deposit        date,
  on_coe            date,
  on_visa           date,
  on_enrolled       date,

  row_hash          bigint not null,
  primary key (load_id, app_uid)
);

create index if not exists apps_scope on applications (load_id, intake_ym);
