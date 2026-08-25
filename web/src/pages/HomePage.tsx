import { Link } from "react-router-dom";

import { useDashboards } from "../api/client";
import { Empty, Spinner } from "../ui/Primitives";

export function HomePage() {
  const { data, isLoading, error } = useDashboards();

  return (
    <>
      <header className="top">
        <div className="top-in">
          <h1>Dashboards</h1>
          <p className="sub">
            Each dashboard owns its own Postgres schema, its own file contracts and its own
            changelog. Uploading to one cannot change what another shows.
          </p>
        </div>
      </header>
      <div className="wrap">
        {isLoading ? <Spinner /> : null}
        {error ? <Empty title="Cannot reach the API">Is the api container running?</Empty> : null}
        {data?.length === 0 ? <Empty title="No dashboards registered" /> : null}
        <div className="cards">
          {data?.map((dashboard) => (
            <Link key={dashboard.slug} to={`/d/${dashboard.slug}`} className="card-link">
              <h2>{dashboard.name}</h2>
              <p className="mono" style={{ fontSize: 11.5 }}>{dashboard.db_schema}</p>
              <div className="meta">
                {dashboard.datasets.map((dataset) => dataset.display_name).join(" · ")}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
