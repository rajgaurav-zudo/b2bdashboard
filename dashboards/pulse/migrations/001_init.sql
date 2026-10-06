-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- Three event tables. Every date here is a day something happened; the page
-- counts the rows whose day falls in the picked range. Area, region and team are
-- stored already defaulted to 'Unassigned', so a filter never has to treat a
-- null specially.

create table if not exists introducers (
  load_id          bigint not null references core.loads(id) on delete cascade,
  partner_name     text   not null,
  introducer_id    text,
  country          text,
  introducer_status text,
  srm_owner        text,
  srm_team         text,                  -- Partner Managed By Team(SRM), for logs without a master row
  area             text   not null,
  region           text   not null,
  team             text   not null,
  became_customer  date,
  row_hash         bigint not null,
  primary key (load_id, partner_name)
);

create index if not exists intro_became on introducers (load_id, became_customer);

create table if not exists applications (
  load_id            bigint not null references core.loads(id) on delete cascade,
  app_uid            text   not null,
  application_id     text,
  student_name       text,
  student_ref        text,
  student_country    text,
  introducer_name    text,
  institution        text,
  course_name        text,
  course_level       text,
  recruitment_type   text,
  application_status text,
  deposit_paid_status text,
  area               text   not null,
  region             text   not null,
  team               text   not null,
  intake_ym          int,                  -- actual intake, year * 100 + month
  at_applied         date,
  at_offer           date,
  at_deposit         date,
  at_coe             date,
  at_visa            date,
  at_enrolled        date,
  at_closed          date,
  row_hash           bigint not null,
  primary key (load_id, app_uid)
);

create index if not exists apps_applied  on applications (load_id, at_applied);
create index if not exists apps_offer    on applications (load_id, at_offer);
create index if not exists apps_deposit  on applications (load_id, at_deposit);
create index if not exists apps_coe      on applications (load_id, at_coe);
create index if not exists apps_visa     on applications (load_id, at_visa);
create index if not exists apps_enrolled on applications (load_id, at_enrolled);
create index if not exists apps_closed   on applications (load_id, at_closed);

create table if not exists logs (
  load_id          bigint not null references core.loads(id) on delete cascade,
  log_uid          text   not null,
  introducer_name  text,
  log_type         text,
  call_type        text,
  outcome          text,
  managed_by_team  text,
  created_by       text,
  logged_on        date,
  note             text,
  row_hash         bigint not null,
  primary key (load_id, log_uid)
);

create index if not exists logs_day on logs (load_id, logged_on);
