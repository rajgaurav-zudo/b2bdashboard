import type { ComponentType } from "react";

import { IntroducerPerformance } from "./introducerPerformance";
import { LogDashboard } from "./logDashboard";

/** Mirror of the backend registry. A dashboard without an entry here still gets
 *  its Data and Changelog tabs; only the bespoke overview is missing. */
export const OVERVIEWS: Record<string, ComponentType<{ slug: string }>> = {
  introducer_performance: IntroducerPerformance,
  logs: LogDashboard,
};
