-- The archive is written gzipped, so the bucket has to accept it.
--
-- Why gzip: Supabase enforces a per-object ceiling at the project level that is
-- independent of the bucket's own file_size_limit, and on the free plan it is
-- 50MB and cannot be raised. The applications export is 114MB, so every upload
-- of it failed at the archive step with EntityTooLarge. Gzipped it is 21MB.
--
-- The bucket's own limit stays at 200MB: it is the smaller of the two that
-- applies, and leaving headroom here means a plan change is the only thing
-- needed to store bigger objects.

update storage.buckets
   set allowed_mime_types = array[
     'text/csv',
     'application/vnd.ms-excel',
     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
     'application/octet-stream',
     'application/gzip'                     -- how the archive is actually written
   ]
 where id = 'uploads';
