-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- The second half of the DAA test. `deferral_initiated` alone is the whole
-- deferral population, and 97% of it has already been approved -- see
-- sources/context.md. Awaiting approval means initiated AND not yet approved,
-- which needs both columns stored.
--
-- Defaults false, like 002: on a load from an export that predates the column,
-- every initiated deferral reads as still awaiting a decision. That is the
-- conservative direction -- it over-reports DAA rather than silently approving
-- deferrals nobody approved.

alter table applications
  add column if not exists deferral_approved boolean not null default false;

drop index if exists applications_deposit_states;
create index if not exists applications_deposit_states
  on applications (load_id, deferral_initiated, deferral_approved, deposit_partial);
