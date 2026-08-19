import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

/* --------------------------------------------------------------------------
   Sign-in state.

   Supabase Auth issues the token; the API decides what it is worth. Nothing here
   grants access -- every data route verifies the signature and checks the
   address against an allow-list server-side. That is why the anon key below is
   safe to ship in the bundle: on its own it reaches the sign-in endpoints and
   nothing else.
   -------------------------------------------------------------------------- */

const URL = import.meta.env.VITE_SUPABASE_URL ?? "";
const ANON = import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";

/** Local development runs with AUTH_REQUIRED=false and no Supabase project, so
 *  the whole sign-in layer stands down rather than blocking on a missing key. */
export const authRequired =
  (import.meta.env.VITE_AUTH_REQUIRED ?? "false").toLowerCase() === "true";

export const supabase: SupabaseClient | null =
  authRequired && URL && ANON ? createClient(URL, ANON) : null;

interface AuthState {
  session: Session | null;
  email: string | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!supabase);

  useEffect(() => {
    if (!supabase) return;
    // an existing session survives a reload, so check before rendering a login form
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => sub.subscription.unsubscribe();
  }, []);

  const value = useMemo<AuthState>(() => ({
    session,
    email: session?.user.email ?? null,
    ready,
    signIn: async (email, password) => {
      if (!supabase) return;
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
    },
    signOut: async () => {
      await supabase?.auth.signOut();
      setSession(null);
    },
  }), [session, ready]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth used outside AuthProvider");
  return ctx;
}

/** Bearer token for the API. Refreshed by supabase-js before it expires, so this
 *  reads the current one rather than caching it. */
export async function accessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
