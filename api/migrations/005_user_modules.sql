-- The modules a member may open: dashboard slugs, plus 'uploads', 'changelog'
-- and 'downloads' for the Data pages. Owners and admins open everything, so
-- for them this is ignored. A key whose dashboard has since been removed is
-- harmless: nothing asks for it any more.
alter table core.users add column if not exists modules text[] not null default '{}';
