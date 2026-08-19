import { Link } from "react-router-dom";

import { useDashboards } from "../api/client";
import { Empty, Spinner } from "../ui/Primitives";

export function HomePage() {
  const { data, isLoading, error } = useDashboards();

  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <div className="brand">
            Dashboards
            <small>Edvoy B2B</small>
          </div>
        </div>
      </header>
      <main className="shell">
        <div className="head">
          <h1>Dashboards</h1>
          <p>
            Each dashboard owns its own Postgres schema, its own file contracts and its own
            changelog. Uploading to one cannot change what another shows.
          </p>
        </div>
        {isLoading ? <Spinner /> : null}
        {error ? <Empty title="Cannot reach the API">Is the api container running?</Empty> : null}
        {data?.length === 0 ? <Empty title="No dashboards registered" /> : null}
        <div className="tiles" style={{ marginTop: 16 }}>
          {data?.map((dashboard) => (
            <Link key={dashboard.slug} to={`/d/${dashboard.slug}`} className="tile" style={{ display: "block" }}>
              <div className="name">{dashboard.db_schema}</div>
              <p className="big" style={{ fontSize: 20 }}>{dashboard.name}</p>
              <div className="foot">
                {dashboard.datasets.map((dataset) => (
                  <span key={dataset.slug}><b>{dataset.display_name}</b></span>
                ))}
              </div>
            </Link>
          ))}
        </div>
      </main>
    </>
  );
}
