-- Region and Team: an application's team is its introducer's SRM team on the
-- introducers master, as on Introducer Performance and Introducer 360.
alter table applications add column if not exists introducer_name text;

create table if not exists introducers (
  load_id      bigint not null references core.loads(id) on delete cascade,
  partner_name text   not null,
  srm_team     text,
  row_hash     bigint not null,
  primary key (load_id, partner_name)
);
