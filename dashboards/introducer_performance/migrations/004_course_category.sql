-- Runs with search_path set to this dashboard's schema. Unqualified names only.
--
-- Course level, and the three categories it collapses into (sources/context.md).
-- Both are stored: the raw level so a miscategorisation can be diagnosed without
-- re-reading the export, and the category so the rule that produced it lives in
-- exactly one place -- ingest.py -- rather than being restated in every query
-- that groups by it.
--
-- `Academic` is the default rather than `Unspecified` for a row that predates the
-- column, because that is what every existing figure already counted: before this
-- column existed, all deposits were reported together, and the deposit numbers
-- are now Academic-only. A load from an older export therefore keeps reporting
-- the same totals instead of collapsing to zero.

alter table applications
  add column if not exists course_level    text,
  add column if not exists course_category text not null default 'Academic';

create index if not exists applications_course_category
  on applications (load_id, course_category);
