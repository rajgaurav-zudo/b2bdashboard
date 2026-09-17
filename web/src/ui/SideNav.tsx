import { useCallback, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useDashboards } from "../api/client";
import { authRequired, useAuth } from "../auth";

const STORE = "b2b.nav.rail";

/** Two letters standing in for the name in the collapsed rail. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "?";
}

/** The frame every page sits in: a navy menu, a white top bar saying where you
 *  are, and the page beneath it.
 *
 *  Two menu groups, because the platform has two kinds of page. A dashboard is
 *  a way of reading the data and each has its own; the files themselves are
 *  shared, so there is one place to upload them and one log of what each
 *  upload changed.
 *
 *  Collapsing narrows the menu to a rail of marks rather than hiding it. At
 *  900px and below the stylesheet lays the menu out as a horizontal row with
 *  every label showing, so the rail preference does not apply there. */
export function AppLayout() {
  const [rail, setRail] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(STORE) === "1";
    } catch {
      return false;
    }
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

  return (
    <div className={`shell${rail ? " rail" : ""}`}>
      <SideNav rail={rail} onToggle={toggle} />
      <main className="main">
        <TopBar />
        <Outlet />
      </main>
    </div>
  );
}

/** Where you are, as plain text. Only the platform root is a link: a crumb for
 *  the page you are on would just reload it. */
function TopBar() {
  const { pathname } = useLocation();
  const { data } = useDashboards();

  let trail: string[];
  if (pathname.startsWith("/d/")) {
    const slug = decodeURIComponent(pathname.split("/")[2] ?? "");
    trail = ["Dashboards", data?.find((d) => d.slug === slug)?.name ?? slug];
  } else if (pathname === "/uploads") {
    trail = ["Data", "Uploads"];
  } else if (pathname === "/changelog") {
    trail = ["Data", "Changelog"];
  } else {
    trail = ["Dashboards"];
  }

  return (
    <header className="topbar">
      <nav aria-label="Breadcrumb">
        <ol className="crumbs">
          {trail.map((crumb, i) => {
            const last = i === trail.length - 1;
            if (last) return <li key={crumb} aria-current="page">{crumb}</li>;
            return (
              <li key={crumb}>
                {crumb === "Dashboards" ? <Link to="/">{crumb}</Link> : crumb}
              </li>
            );
          })}
        </ol>
      </nav>
    </header>
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

      <nav className="nav-list" aria-label="Main">
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
          {/* a delta, not a cycle glyph: Inter has no arrow-circle and the
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
