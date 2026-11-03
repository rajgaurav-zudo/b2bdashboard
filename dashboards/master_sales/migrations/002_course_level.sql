-- Application Course Level, and the group it falls in: Academic, Language or
-- Other (a blank, a level in neither list, a stray value). See context.md.

alter table applications add column if not exists course_level text;
alter table applications add column if not exists level_group  text not null default 'Other';
