import { HashRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui/Toast";
import { OverviewPage } from "@/pages/OverviewPage";
import { PeoplePage } from "@/pages/PeoplePage";
import { PersonDetailPage } from "@/pages/PersonDetailPage";
import { CapturePage } from "@/pages/CapturePage";
import { AuditPage } from "@/pages/AuditPage";
import { SpacesPage } from "@/pages/SpacesPage";
import { SpaceDetailPage } from "@/pages/SpaceDetailPage";

function LegacyCaptureRedirect() {
  return <Navigate to="/people" replace />;
}

function LegacyGalleryRedirect() {
  const { userId } = useParams();
  if (userId) return <Navigate to={`/people/${userId}`} replace />;
  return <Navigate to="/people" replace />;
}

function Workbench() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/spaces" element={<SpacesPage />} />
        <Route path="/spaces/:spaceId" element={<SpaceDetailPage />} />
        <Route path="/people" element={<PeoplePage />} />
        <Route path="/people/:userId" element={<PersonDetailPage />} />
        <Route path="/people/:userId/capture" element={<CapturePage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/gallery" element={<Navigate to="/people" replace />} />
        <Route path="/gallery/:userId" element={<LegacyGalleryRedirect />} />
        <Route path="/capture" element={<LegacyCaptureRedirect />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <HashRouter>
        <Workbench />
      </HashRouter>
    </ToastProvider>
  );
}
