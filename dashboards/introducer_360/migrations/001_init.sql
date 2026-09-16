-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- The table this dashboard exists for is `applications`, and what makes it
-- different from the introducer performance dashboard's table of the same name
-- is the ten `at_*` columns. The applications export carries a timestamp for
-- every status an application has passed through -- Draft, Ready to Apply,
-- Applied, Offer, Deposit Fully Paid, CoE Received, Visa Applied, Visa Granted,
-- Enrolled. Those columns are what turn a snapshot of current statuses into a
-- pipeline you can put a date range across: a stage's count is the number of
-- applications that *entered* it inside the window, not the number sitting in it
-- when the file was exported.
--
-- Dates, not timestamps. Every one of these columns arrives as midnight in the
-- export -- there is no time of day in the data -- and a date is what the range
-- filter compares against, so storing a timestamptz would only invite a timezone
-- to move a row across a day boundary that the CRM never recorded.

create table if not exists applications (
  load_id                bigint not null references core.loads(id) on delete cascade,
  app_uid                text   not null,
  application_id         text,
  introducer_name        text,

  -- the pipeline, in funnel order
  at_draft               date,
  at_ready               date,
  at_applied             date,
  at_offer               date,
  at_deposit             date,          -- 'Deposit Fully Paid'
  at_coe                 date,
  at_visa_applied        date,
  at_visa_granted        date,
  at_enrolled            date,
  -- the earliest of the above: when this application entered the pipeline at
  -- all. It is the date anchor for the two stages that are states rather than
  -- events (partial deposit, deferral) -- see context.md.
  at_entered             date,

  -- state, as the platform defines it (sources/context.md)
  deposit_paid_status    text,
  deposit_fully_paid     boolean not null default false,
  deposit_partial        boolean not null default false,
  deferral_initiated     boolean not null default false,
  deferral_approved      boolean not null default false,
  closed_lost            boolean not null default false,

  course_level           text,
  course_category        text not null default 'Academic',
  intake_month           text,
  intake_year            int,
  cycle_index            smallint,      -- 0 Jan · 1 May · 2 Sep · null unknown
  application_status     text,
  application_sub_status text,

  row_hash               bigint not null,
  primary key (load_id, app_uid)
);

-- Every query this dashboard runs is (load, introducer) narrowed by a date on
-- one of the at_* columns and grouped by stage. The introducer index carries the
-- filter; the stage dates are read in one pass over what it returns, which is
-- why there are no ten separate date indexes here.
create index if not exists apps_introducer on applications (load_id, introducer_name);
create index if not exists apps_intake on applications (load_id, intake_year, cycle_index);
create index if not exists apps_entered on applications (load_id, at_entered);

create table if not exists introducers (
  load_id                bigint not null references core.loads(id) on delete cascade,
  partner_name           text   not null,
  lifecycle_stage        text,
  latest_contract_status text,
  country                text,
  srm_team               text,
  srm_owner              text,
  became_customer_date   date,
  became_customer_year   int,
  row_hash               bigint not null,
  primary key (load_id, partner_name)
);
create index if not exists introducers_team on introducers (load_id, srm_team);
