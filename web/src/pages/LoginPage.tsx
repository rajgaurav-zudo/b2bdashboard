import { useState } from "react";

import { useAuth } from "../auth";

export function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      // Supabase returns the same message for a wrong password and an unknown
      // address, deliberately: distinguishing them tells an attacker which
      // addresses exist. Passing it through keeps that property.
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <header className="top">
        <div className="top-in">
          <p className="eyebrow">Edvoy B2B</p>
          <h1>Dashboards</h1>
        </div>
      </header>
      <div className="wrap">
        <form className="signin" onSubmit={submit}>
          <h2>Sign in</h2>
          <p>These dashboards carry partner commission terms. Access is by invitation.</p>

          <label htmlFor="email">Email</label>
          <input
            id="email" type="email" autoComplete="username" required
            value={email} onChange={(e) => setEmail(e.target.value)}
          />

          <label htmlFor="password">Password</label>
          <input
            id="password" type="password" autoComplete="current-password" required
            value={password} onChange={(e) => setPassword(e.target.value)}
          />

          {error ? <p className="status err">{error}</p> : null}

          <button type="submit" className="btn" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </>
  );
}

/** Shown when the token is valid but the address is not on the API's list. The
 *  difference matters: signing in again cannot fix it. */
export function NotPermitted({ email, detail, onSignOut }: {
  email: string | null; detail: string; onSignOut: () => void;
}) {
  return (
    <>
      <header className="top">
        <div className="top-in">
          <p className="eyebrow">Edvoy B2B</p>
          <h1>Dashboards</h1>
        </div>
      </header>
      <div className="wrap">
        <div className="signin">
          <h2>No access</h2>
          <p>
            You are signed in as <b>{email}</b>, but that account is not permitted to use these
            dashboards. {detail}
          </p>
          <p>Ask whoever administers the project to add your address, then sign in again.</p>
          <button type="button" className="btn" onClick={onSignOut}>Sign out</button>
        </div>
      </div>
    </>
  );
}
