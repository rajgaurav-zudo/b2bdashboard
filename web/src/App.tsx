import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { ApiError } from "./api/client";
import { authRequired, supabase, useAuth } from "./auth";
import { ChangelogPage } from "./pages/ChangelogPage";
import { DashboardShell } from "./pages/DashboardShell";
import { DataPage } from "./pages/DataPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage, NotPermitted } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { Spinner } from "./ui/Primitives";

export function App() {
  const { session, email, ready, signOut } = useAuth();
  const [forbidden, setForbidden] = useState<string | null>(null);

  // A 403 anywhere means the token is good but this account is not on the API's
  // list. Caught globally because it is not a property of any one page.
  useEffect(() => {
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      if (reason instanceof ApiError && reason.status === 403) setForbidden(reason.message);
    };
    window.addEventListener("unhandledrejection", onRejection);
    return () => window.removeEventListener("unhandledrejection", onRejection);
  }, []);

  if (authRequired) {
    if (!supabase) {
      return (
        <div className="wrap">
          <div className="signin">
            <h2>Not configured</h2>
            <p>
              Auth is switched on but <code>VITE_SUPABASE_URL</code> and{" "}
              <code>VITE_SUPABASE_ANON_KEY</code> are not set, so there is no way to sign in.
            </p>
          </div>
        </div>
      );
    }
    if (!ready) return <Spinner label="Checking your session…" />;
    if (!session) return <LoginPage />;
    if (forbidden) {
      return <NotPermitted email={email} detail={forbidden} onSignOut={() => {
        setForbidden(null);
        void signOut();
      }} />;
    }
  }

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/d/:slug" element={<DashboardShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="data" element={<DataPage />} />
        <Route path="changelog" element={<ChangelogPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
