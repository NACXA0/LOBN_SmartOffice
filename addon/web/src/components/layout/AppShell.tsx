import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { BottomNav } from "./BottomNav";
import { StatusBar } from "./StatusBar";
import { AssistantDrawer } from "@/components/AssistantDrawer";

export function AppShell() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <Outlet />
      </main>
      <StatusBar />
      <BottomNav />
      <AssistantDrawer />
    </div>
  );
}
