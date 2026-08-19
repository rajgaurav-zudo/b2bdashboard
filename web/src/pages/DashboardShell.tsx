import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { useDashboard } from "../api/client";
import { authRequired, useAuth } from "../auth";
import { Empty, Spinner } from "../ui/Primitives";

export function DashboardShell() {
  const { slug = "" } = useParams();
  const { data, isLoading, error } = useDashboard(slug);
  const { email, signOut } = useAuth();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "on" : "");

  return (
    <>
      <header className="top">
        <div className="top-in">
          <div className="row">
            <div>
              <Link to="/" className="back">← All dashboards</Link>
              <h1>{data?.name ?? slug}</h1>
              <p className="sub">
                Which recruitment partners used to pay us and stopped — and who to call first to win
                them back. Deposit counts are the revenue proxy; commission value is not in either
                export.
              </p>
            </div>
            <nav className="nav">
              <NavLink end to={`/d/${slug}`} className={link}>Overview</NavLink>
              <NavLink to={`/d/${slug}/data`} className={link}>Data</NavLink>
              <NavLink to={`/d/${slug}/changelog`} className={link}>Changelog</NavLink>
              {authRequired && email ? (
                <button type="button" className="signout" onClick={() => void signOut()}
                        title={`Signed in as ${email}`}>
                  Sign out
                </button>
              ) : null}
            </nav>
          </div>
        </div>
      </header>
      <div className="wrap">
        {isLoading ? <Spinner /> : null}
        {error ? <Empty title="Unknown dashboard">Nothing is registered under “{slug}”.</Empty> : null}
        {data ? <Outlet context={data} /> : null}
      </div>
    </>
  );
}
