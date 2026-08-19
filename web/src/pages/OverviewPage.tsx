import { useOutletContext } from "react-router-dom";

import type { DashboardDetail } from "../api/types";
import { OVERVIEWS } from "../dashboards/registry";
import { Empty } from "../ui/Primitives";

export function OverviewPage() {
  const dashboard = useOutletContext<DashboardDetail>();
  const Overview = OVERVIEWS[dashboard.slug];

  if (!Overview) {
    return (
      <Empty title="No overview built for this dashboard yet">
        <p>
          The data pipeline works — use the <b>Data</b> and <b>Changelog</b> tabs. Add a component to{" "}
          <code>web/src/dashboards/registry.tsx</code> to give it an overview.
        </p>
      </Empty>
    );
  }
  return <Overview slug={dashboard.slug} />;
}
