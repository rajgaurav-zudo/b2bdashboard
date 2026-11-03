-- When a deposit was part paid and when a deferral was initiated and approved,
-- so PD and DAA follow the date range like the stages. Older exports leave them
-- null. See context.md.

alter table applications add column if not exists on_pd                 date;
alter table applications add column if not exists on_deferral_initiated date;
alter table applications add column if not exists on_deferral_approved  date;
alter table applications add column if not exists deferral_initiated    boolean not null default false;
alter table applications add column if not exists deferral_approved     boolean not null default false;
