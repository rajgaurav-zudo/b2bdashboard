import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import type { ReactNode } from "react";

import { ApiError } from "./api/client";
import { authConfigured, authRequired, useAuth } from "./auth";
import { ChangelogPage } from "./pages/ChangelogPage";
import { DashboardShell } from "./pages/DashboardShell";
import { DataPage } from "./pages/DataPage";
import { DownloadsPage } from "./pages/DownloadsPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage, NotPermitted } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { UsersPage } from "./pages/UsersPage";
import { AppLayout } from "./ui/SideNav";
import { Empty } from "./ui/Primitives";

export function App() {
  const { session, email, signOut } = useAuth();
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
    if (!authConfigured) {
      return (
        <div className="wrap">
          <div className="signin">
            <h2>Not configured</h2>
            <p>
              Auth is switched on but <code>GOOGLE_CLIENT_ID</code> is not set, so there is no
              way to sign in.
            </p>
          </div>
        </div>
      );
    }
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
        <Route path="/uploads" element={<Gate module="uploads"><DataPage /></Gate>} />
        <Route path="/changelog" element={<Gate module="changelog"><ChangelogPage /></Gate>} />
        <Route path="/downloads" element={<Gate module="downloads"><DownloadsPage /></Gate>} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/d/:slug" element={<DashboardGate />}>
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

/** A module this user was not given. Saying so beats a page of failed calls:
 *  the API refuses them all anyway. */
function Gate({ module, children }: { module: string; children: ReactNode }) {
  const { can } = useAuth();
  if (can(module)) return <>{children}</>;
  return (
    <div className="wrap">
      <Empty title="You do not have access to this">Ask an admin to give it to you on the Users page.</Empty>
    </div>
  );
}

function DashboardGate() {
  const { slug = "" } = useParams();
  return <Gate module={slug}><DashboardShell /></Gate>;
}

function MovedToPlatform({ page }: { page: "uploads" | "changelog" }) {
  const { slug = "" } = useParams();
  return <Navigate to={`/${page}?dashboard=${encodeURIComponent(slug)}`} replace />;
}
