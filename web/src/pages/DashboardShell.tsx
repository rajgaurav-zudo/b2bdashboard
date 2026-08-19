import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { useDashboard } from "../api/client";
import { Empty, Spinner } from "../ui/Primitives";

export function DashboardShell() {
  const { slug = "" } = useParams();
  const { data, isLoading, error } = useDashboard(slug);

  const tab = ({ isActive }: { isActive: boolean }) => `tab${isActive ? " on" : ""}`;

  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <div className="brand">
            <Link to="/" style={{ color: "inherit" }}>{data?.name ?? slug}</Link>
            <small>Edvoy B2B · {slug}</small>
          </div>
          <nav className="tabs">
            <NavLink end to={`/d/${slug}`} className={tab}>Overview</NavLink>
            <NavLink to={`/d/${slug}/data`} className={tab}>Data</NavLink>
            <NavLink to={`/d/${slug}/changelog`} className={tab}>Changelog</NavLink>
          </nav>
        </div>
      </header>
      <main className="shell">
        {isLoading ? <Spinner /> : null}
        {error ? <Empty title="Unknown dashboard">Nothing is registered under “{slug}”.</Empty> : null}
        {data ? <Outlet context={data} /> : null}
      </main>
    </>
  );
}
