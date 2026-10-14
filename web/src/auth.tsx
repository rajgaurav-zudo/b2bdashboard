import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/* --------------------------------------------------------------------------
   Sign-in state.

   Google says who someone is; the API decides what that is worth. The button
   yields a Google ID token, the API checks it and the account's domain, and
   answers with a session token of its own -- which is what is kept here and
   sent with every request. Nothing in this file grants access: the domain
   below only tells Google which accounts to offer, and the client ID is safe
   to ship in the bundle because on its own it reaches nothing.
   -------------------------------------------------------------------------- */

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

/** The Workspace the account chooser is narrowed to. A hint for Google, not a
 *  check: the API enforces its own list and refuses everything else. */
export const SIGN_IN_DOMAIN = "edvoy.com";

/** Local development runs with AUTH_REQUIRED=false and no Google client, so
 *  the whole sign-in layer stands down rather than blocking on a missing ID. */
export const authRequired =
  (import.meta.env.VITE_AUTH_REQUIRED ?? "false").toLowerCase() === "true";

export const authConfigured = authRequired && CLIENT_ID !== "";

export type Role = "owner" | "admin" | "member";

export interface Session {
  token: string;
  email: string;
  name: string;
  /** as of sign-in; refreshed from /api/auth/me on load, since an admin may
   *  have changed it since */
  role: Role;
  /** seconds since the epoch, as the API reports it */
  expires_at: number;
}

const STORE = "b2b.session";
const CHANGED = "b2b:session";

const live = (s: Session | null): Session | null =>
  s && s.expires_at * 1000 > Date.now() ? s : null;

function stored(): Session | null {
  try {
    return live(JSON.parse(localStorage.getItem(STORE) ?? "null") as Session | null);
  } catch {
    return null;
  }
}

/** Kept at module level as well as in React state so the API client, which is
 *  not a component, reads the same session the page is showing. */
let current: Session | null = authConfigured ? stored() : null;

function setCurrent(next: Session | null) {
  current = next;
  try {
    if (next) localStorage.setItem(STORE, JSON.stringify(next));
    else localStorage.removeItem(STORE);
  } catch { /* a private window without storage still works until it is reloaded */ }
  window.dispatchEvent(new Event(CHANGED));
}

/** Bearer token for the API, or null when signed out or expired. */
export async function accessToken(): Promise<string | null> {
  return live(current)?.token ?? null;
}

/** The API answered 401: whatever is held no longer works, so drop it and let
 *  the sign-in page come back. */
export function sessionRejected() {
  if (current) setCurrent(null);
}

interface AuthState {
  session: Session | null;
  email: string | null;
  role: Role | null;
  /** may open the Users page. The API checks again on every call. */
  isAdmin: boolean;
  signIn: (credential: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(current);

  useEffect(() => {
    const sync = () => setSession(current);
    // another tab signing in or out writes the same key
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORE) return;
      current = authConfigured ? stored() : null;
      sync();
    };
    window.addEventListener(CHANGED, sync);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(CHANGED, sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  // the role may have changed since sign-in; ask once per page load
  const token = session?.token;
  useEffect(() => {
    if (!token) return;
    let stale = false;
    void fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } }).then(async (res) => {
      if (stale || !current || current.token !== token) return;
      if (res.status === 401) return sessionRejected();
      if (!res.ok) return;
      const me = await res.json() as { name: string; role: Role };
      if (current.role !== me.role || current.name !== me.name) setCurrent({ ...current, ...me });
    });
    return () => { stale = true; };
  }, [token]);

  // sign out at the moment the session lapses rather than on the next failed call
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => setCurrent(null), session.expires_at * 1000 - Date.now());
    return () => window.clearTimeout(timer);
  }, [session]);

  const value = useMemo<AuthState>(() => ({
    session,
    email: session?.email ?? null,
    role: session?.role ?? null,
    isAdmin: session?.role === "owner" || session?.role === "admin",
    signIn: async (credential) => {
      const res = await fetch("/api/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(typeof body?.detail === "string" ? body.detail : res.statusText);
      setCurrent(body as Session);
    },
    signOut: async () => {
      // otherwise Google signs the same account straight back in
      window.google?.accounts.id.disableAutoSelect();
      setCurrent(null);
    },
  }), [session]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth used outside AuthProvider");
  return ctx;
}

/* --------------------------------------------------------------------------
   Google Identity Services. Loaded on demand: only the sign-in page needs it.
   -------------------------------------------------------------------------- */

interface GoogleId {
  initialize: (config: {
    client_id: string;
    callback: (response: { credential?: string }) => void;
    hd?: string;
    ux_mode?: "popup" | "redirect";
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, string | number>) => void;
  disableAutoSelect: () => void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

let gsi: Promise<GoogleId> | null = null;

function loadGoogle(): Promise<GoogleId> {
  gsi ??= new Promise<GoogleId>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () =>
      window.google ? resolve(window.google.accounts.id) : reject(new Error("Google sign-in did not load"));
    script.onerror = () => {
      gsi = null;       // let a retry try again
      reject(new Error("Could not reach Google to sign in. Check your connection and reload."));
    };
    document.head.appendChild(script);
  });
  return gsi;
}

/** Draw Google's own button into `parent`; `onCredential` receives the ID token. */
export async function renderGoogleButton(parent: HTMLElement, onCredential: (credential: string) => void) {
  const google = await loadGoogle();
  google.initialize({
    client_id: CLIENT_ID,
    hd: SIGN_IN_DOMAIN,
    ux_mode: "popup",
    callback: ({ credential }) => { if (credential) onCredential(credential); },
  });
  google.renderButton(parent, { type: "standard", theme: "outline", size: "large", text: "signin_with", width: 320 });
}
