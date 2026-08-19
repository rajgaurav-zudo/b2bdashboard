import { Navigate, Route, Routes } from "react-router-dom";

import { ChangelogPage } from "./pages/ChangelogPage";
import { DashboardShell } from "./pages/DashboardShell";
import { DataPage } from "./pages/DataPage";
import { HomePage } from "./pages/HomePage";
import { OverviewPage } from "./pages/OverviewPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/d/:slug" element={<DashboardShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="data" element={<DataPage />} />
        <Route path="changelog" element={<ChangelogPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
