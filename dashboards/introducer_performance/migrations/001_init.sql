-- Runs with search_path set to this dashboard's schema. Unqualified names only.

create table if not exists introducers (
  load_id                  bigint not null references core.loads(id) on delete cascade,
  partner_name             text   not null,
  lifecycle_stage          text,
  latest_contract_status   text,
  country                  text,
  srm_team                 text,
  srm_owner                text,
  became_customer_date     date,
  became_customer_year     int,          -- survives dates that will not parse
  source_created_at        date,
  source_created_year      int,
  org_commission           text,
  contract_commission_type text,
  row_hash                 bigint not null,
  primary key (load_id, partner_name)
);
create index if not exists introducers_stage on introducers (load_id, lifecycle_stage);
create index if not exists introducers_country on introducers (load_id, country);

create table if not exists applications (
  load_id                bigint not null references core.loads(id) on delete cascade,
  app_uid                text   not null,
  application_id         text,
  introducer_name        text,
  deposit_paid_status    text,
  deposit_fully_paid     boolean not null default false,
  closed_lost            boolean not null default false,
  intake_month           text,
  intake_year            int,
  cycle_year             int,           -- Nov/Dec roll into the following January
  cycle_index            smallint,      -- 0 Jan · 1 May · 2 Sep · null unknown
  application_status     text,
  application_sub_status text,
  visa_granted           boolean not null default false,
  visa_granted_at        timestamptz,
  enrolled               boolean not null default false,
  enrolled_at            timestamptz,
  row_hash               bigint not null,
  primary key (load_id, app_uid)
);
create index if not exists applications_introducer on applications (load_id, introducer_name);
create index if not exists applications_cycle on applications (load_id, cycle_year);
create index if not exists applications_deposits on applications (load_id, deposit_fully_paid, closed_lost);
