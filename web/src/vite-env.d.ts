/// <reference types="vite/client" />

/** The build-time settings this app reads. Vite only exposes VITE_-prefixed
 *  variables to the bundle, which is the mechanism keeping the service role key
 *  out of it: that one is never named VITE_*. */
interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  readonly VITE_AUTH_REQUIRED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
