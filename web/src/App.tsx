import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { ApiError } from "./api/client";
import { authRequired, supabase, useAuth } from "./auth";
import { ChangelogPage } from "./pages/ChangelogPage";
import { DashboardShell } from "./pages/DashboardShell";
import { DataPage } from "./pages/DataPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage, NotPermitted } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { Spinner } from "./ui/Primitives";
import { AppLayout } from "./ui/SideNav";

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
      {/* every page hangs off the layout, so the menu is drawn once and does
          not remount -- and cannot scroll away -- as you move between them */}
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        {/* uploads and their changelog are platform-level: one file feeds every
            dashboard that declares its source, so there is one place to put it
            and one log of what it did */}
        <Route path="/uploads" element={<DataPage />} />
        <Route path="/changelog" element={<ChangelogPage />} />
        <Route path="/d/:slug" element={<DashboardShell />}>
          <Route index element={<OverviewPage />} />
        </Route>
        {/* these were tabs inside a dashboard until the move; a bookmark still
            lands on the right table, filtered to the dashboard it named */}
        <Route path="/d/:slug/data" element={<MovedToPlatform page="uploads" />} />
        <Route path="/d/:slug/changelog" element={<MovedToPlatform page="changelog" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function MovedToPlatform({ page }: { page: "uploads" | "changelog" }) {
  const { slug = "" } = useParams();
  return <Navigate to={`/${page}?dashboard=${encodeURIComponent(slug)}`} replace />;
}
