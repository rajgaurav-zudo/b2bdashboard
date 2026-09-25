import type { ComponentType } from "react";

import { Introducer360 } from "./introducer360";
import { IntroducerPerformance } from "./introducerPerformance";
import { LogDashboard } from "./logDashboard";
import { Pipeline } from "./pipeline";

/** Mirror of the backend registry. A dashboard without an entry here still gets
 *  its Data and Changelog tabs; only the bespoke overview is missing. */
export const OVERVIEWS: Record<string, ComponentType<{ slug: string }>> = {
  introducer_performance: IntroducerPerformance,
  introducer_360: Introducer360,
  logs: LogDashboard,
  pipeline: Pipeline,
};
