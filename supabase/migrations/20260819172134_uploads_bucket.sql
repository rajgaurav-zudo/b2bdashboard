-- Private bucket for the raw CRM exports.
--
-- Scope: platform config only. The application schema -- core.* and every
-- dash_<slug> -- is created by the app's own migration runner on API startup
-- and must not be declared here. See supabase/README.md.

-- 200MB: the applications export is already 114MB, and Supabase's own default
-- of 50MB would reject it at the upload step rather than at validation.
-- storage.file_size_limit in config.toml has to match, and the project-level
-- cap in Settings > Storage has to be at least this.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'uploads',
  'uploads',
  false,                                  -- these are CRM extracts, never public
  209715200,
  array[
    'text/csv',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/octet-stream'            -- browsers send this for .xlsx often enough
  ]
)
on conflict (id) do update
  set public            = excluded.public,
      file_size_limit   = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- No policies on storage.objects for this bucket, deliberately.
--
-- RLS is enabled on storage.objects by Supabase, and policies are additive: with
-- none granting access to 'uploads', neither `anon` nor `authenticated` can read,
-- list or write it. The API reaches it with the service role key, which bypasses
-- RLS entirely, so uploads keep going through the ingest pipeline -- the only path
-- that parses, diffs and records a load.
--
-- If a policy is ever added here to let the browser upload directly, note what
-- that costs: a file in the bucket with no matching core.uploads row is invisible
-- to the changelog and to rollback.
