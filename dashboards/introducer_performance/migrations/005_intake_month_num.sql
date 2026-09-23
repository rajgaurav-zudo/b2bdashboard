-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- The intake month as a number, for the dashboard's date range. The range is an
-- intake-period window (sources/context.md: `Actual Intake Year` and `Actual
-- Intake Month`, no other date), and a window from September to May cannot be
-- tested against a month name.
--
-- Stored rather than parsed at read time, like every other derived column here:
-- the parsing rule lives in ingest.py (`_month_number`). The update below is a
-- one-off backfill of loads made before this column existed, and repeats that
-- rule once for them -- a full month name or its first three letters, or a bare
-- 1-12. New loads never reach it; ingest writes the column.

alter table applications
  add column if not exists intake_month_num smallint;

update applications
   set intake_month_num = case
         when intake_month ~ '^\s*\d{1,2}\s*$'
              and trim(intake_month)::int between 1 and 12 then trim(intake_month)::int
         else array_position(
                array['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'],
                left(lower(trim(intake_month)), 3))
       end
 where intake_month_num is null and intake_month is not null;
