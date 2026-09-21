-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- The three deposit states (see sources/context.md). `deposit_fully_paid` on its
-- own could not tell a seat in this intake from a deposit whose intake has been
-- deferred, or from a commitment that has not cleared -- both were being counted
-- as ordinary deposits or not at all.
--
-- Both are stored rather than derived at read time, for the same reason
-- `deposit_fully_paid` is: the normalisation rule (lowercase, strip whitespace)
-- lives in ingest.py, and a second copy of it in SQL is a second place to be
-- wrong. Older exports carry neither column; they default false, so a load from
-- a file that predates them reads as "no deferrals, no partials" rather than
-- failing.

alter table applications
  add column if not exists deposit_partial    boolean not null default false,
  add column if not exists deferral_initiated boolean not null default false;

create index if not exists applications_deposit_states
  on applications (load_id, deferral_initiated, deposit_partial);
