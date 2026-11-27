import { LayoutDashboard, Users, Activity, MapPinned } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavId = "overview" | "spaces" | "people" | "audit";

export type NavItem = {
  id: NavId;
  label: string;
  path: string;
  icon: LucideIcon;
  group: "workbench" | "floor";
};

export const NAV_GROUPS: { id: "workbench" | "floor"; label: string }[] = [
  { id: "workbench", label: "工作台" },
  { id: "floor", label: "现场" },
];

/** 总管视角：总览 / 空间 / 人员 / 记录 */
export const NAV: NavItem[] = [
  { id: "overview", label: "总览", path: "/overview", icon: LayoutDashboard, group: "workbench" },
  { id: "spaces", label: "空间", path: "/spaces", icon: MapPinned, group: "floor" },
  { id: "people", label: "人员", path: "/people", icon: Users, group: "floor" },
  { id: "audit", label: "记录", path: "/audit", icon: Activity, group: "floor" },
];
