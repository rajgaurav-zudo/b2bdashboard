import { Outlet, useParams } from "react-router-dom";

import { useDashboard } from "../api/client";
import { Empty, Spinner } from "../ui/Primitives";

/** The header above a dashboard's pages. The tabs and the way back out both
 *  live in the left menu now, so this only has to say what you are looking at. */
export function DashboardShell() {
  const { slug = "" } = useParams();
  const { data, isLoading, error } = useDashboard(slug);

  return (
    <>
      <header className="top">
        <div className="top-in">
          <h1>{data?.name ?? slug}</h1>
          {data?.description ? <p className="sub">{data.description}</p> : null}
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
