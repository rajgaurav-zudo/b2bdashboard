import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useDashboards } from "../api/client";
import { authRequired, useAuth } from "../auth";

const STORE = "b2b.nav.rail";

/** Two letters standing in for the name in the collapsed rail. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "?";
}

/** The frame every page sits in: a left menu, and the page beside it.
 *
 *  Two groups, because the platform has two kinds of page. A dashboard is a way
 *  of reading the data and each has its own; the files themselves are shared, so
 *  there is one place to upload them and one log of what each upload changed.
 *
 *  Collapsing narrows the menu to a rail of marks rather than hiding it, so the
 *  page never loses the thing that says where you are. Below 860px the rail is
 *  the default and expanding it floats over the page instead of squeezing it. */
export function AppLayout() {
  const [rail, setRail] = useState<boolean>(() => {
    try {
      const saved = window.localStorage.getItem(STORE);
      if (saved !== null) return saved === "1";
    } catch {
      /* private browsing: fall through to the width default */
    }
    return window.innerWidth <= 860;
  });

  const toggle = useCallback(() => {
    setRail((was) => {
      try {
        window.localStorage.setItem(STORE, was ? "0" : "1");
      } catch {
        /* the preference is a convenience, not state the app depends on */
      }
      return !was;
    });
  }, []);

  const { pathname } = useLocation();

  // on a phone the expanded menu covers the page, so a tap through to a new
  // page has to close it -- otherwise you land behind the menu you just used
  useEffect(() => {
    if (window.innerWidth <= 860) setRail(true);
  }, [pathname]);

  return (
    <div className={`shell${rail ? " rail" : ""}`}>
      <SideNav rail={rail} onToggle={toggle} />
      {/* only ever visible under the floating menu on a narrow screen */}
      <div className="nav-scrim" onClick={() => setRail(true)} aria-hidden="true" />
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

function SideNav({ rail, onToggle }: { rail: boolean; onToggle: () => void }) {
  const { data, isLoading, error } = useDashboards();
  const { email, signOut } = useAuth();

  return (
    <aside className="sidenav">
      <div className="nav-brand">
        <Link to="/" className="mark" title="All dashboards">EB</Link>
        <Link to="/" className="wordmark">
          <b>Edvoy B2B</b>
          <span>Dashboards</span>
        </Link>
        <button
          type="button"
          className="rail-t"
          onClick={onToggle}
          title={rail ? "Expand the menu" : "Collapse the menu"}
          aria-label={rail ? "Expand the menu" : "Collapse the menu"}
          aria-expanded={!rail}
        >
          {rail ? "»" : "«"}
        </button>
      </div>

      <nav className="nav-list">
        <div className="nav-group">
          <p className="nav-lbl">Dashboards</p>
          {isLoading ? <p className="nav-note">Loading…</p> : null}
          {error ? <p className="nav-note bad">API unreachable</p> : null}
          {data?.map((dashboard) => (
            <Row key={dashboard.slug} to={`/d/${dashboard.slug}`} rail={rail}
                 mark={initials(dashboard.name)} label={dashboard.name} />
          ))}
        </div>

        {/* one place for every file, whichever dashboard reads it */}
        <div className="nav-group">
          <p className="nav-lbl">Data</p>
          <Row to="/uploads" rail={rail} mark="↑" label="Uploads"
               hint="Send a file to every dashboard that reads it" />
          {/* a delta, not a cycle glyph: IBM Plex has no arrow-circle and the
              fallback rendered as a dot */}
          <Row to="/changelog" rail={rail} mark="Δ" label="Changelog"
               hint="What every upload changed, in every dashboard" />
        </div>
      </nav>

      {authRequired && email ? (
        <div className="nav-foot">
          <span className="em" title={email}>{email}</span>
          <button
            type="button"
            className="out"
            onClick={() => void signOut()}
            title={`Sign out of ${email}`}
            aria-label="Sign out"
          >
            <span className="lb">Sign out</span>
            <span className="ic" aria-hidden="true">⎋</span>
          </button>
        </div>
      ) : null}
    </aside>
  );
}

function Row({ to, rail, mark, label, hint }: {
  to: string; rail: boolean; mark: string; label: string; hint?: string;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => (isActive ? "nav-d on" : "nav-d")}
      title={rail ? (hint ?? label) : hint}
    >
      {/* a glyph needs to be set larger than a pair of initials to read at all */}
      <span className={mark.length === 1 ? "sq g" : "sq"} aria-hidden="true">{mark}</span>
      <span className="lb">{label}</span>
    </NavLink>
  );
}
