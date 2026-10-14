import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { SIGN_IN_DOMAIN, renderGoogleButton, useAuth } from "../auth";

/** The one card on an otherwise empty page, for every signed-out state. */
function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="login">
      <div className="login-card">
        <div className="login-brand">
          <span className="mark" aria-hidden="true">EB</span>
          <div>
            <b>Edvoy B2B</b>
            <span>Dashboards</span>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

export function LoginPage() {
  const { signIn } = useAuth();
  const button = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!button.current) return;
    renderGoogleButton(button.current, (credential) => {
      setBusy(true);
      setError(null);
      // The API's answer is shown as it is: for an account that has not been
      // added it says who to ask, which is the one thing the person can act on.
      signIn(credential)
        .catch((err: Error) => setError(err.message))
        .finally(() => setBusy(false));
    }).catch((err: Error) => setError(err.message));
  }, [signIn]);

  return (
    <Frame>
      <h1>Sign in</h1>
      <p>Use your <b>@{SIGN_IN_DOMAIN}</b> Google account.</p>

      <div className="google" ref={button} />

      {busy ? <p className="status">Signing in…</p> : null}
      {error ? <p className="status err" role="alert">{error}</p> : null}

      <p className="login-foot">
        Access is by invitation. If Google signs you in but the dashboard does not, ask an admin to
        add you.
      </p>
    </Frame>
  );
}

/** Shown when the token is valid but the address is not on the API's list. The
 *  difference matters: signing in again cannot fix it. */
export function NotPermitted({ email, detail, onSignOut }: {
  email: string | null; detail: string; onSignOut: () => void;
}) {
  return (
    <Frame>
      <h1>No access</h1>
      <p>
        You are signed in as <b>{email}</b>, but that account is not permitted to use these
        dashboards. {detail}
      </p>
      <button type="button" className="btn" onClick={onSignOut}>Sign out</button>
    </Frame>
  );
}
