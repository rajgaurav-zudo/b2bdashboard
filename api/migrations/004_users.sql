-- Who may use the dashboards.
--
-- The Google domain check says someone works here; this table says they have
-- been given access. Both must hold to sign in.
--
--   owner   one person, set by AUTH_OWNER_EMAIL and rewritten at every boot.
--           Cannot be changed or removed from the app.
--   admin   manages members.
--   member  uses the dashboards.

create table if not exists core.users (
  email           text primary key check (email = lower(btrim(email)) and email like '%_@_%'),
  name            text not null default '',
  role            text not null default 'member' check (role in ('owner', 'admin', 'member')),
  active          boolean not null default true,
  added_by        text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  last_sign_in_at timestamptz
);

-- one owner at a time
create unique index if not exists users_one_owner on core.users ((true)) where role = 'owner';
