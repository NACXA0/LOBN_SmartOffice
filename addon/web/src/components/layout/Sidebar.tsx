import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import * as Tooltip from "@radix-ui/react-tooltip";
import { Building2, PanelLeftClose, PanelLeft } from "lucide-react";
import { NAV, NAV_GROUPS } from "./nav";

const KEY = "smartoffice_sidebar_collapsed";

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(KEY) === "1";
    } catch {
      return false;
    }
  });
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const apply = () => setNarrow(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const icon = collapsed || narrow;
    root.style.setProperty("--sidebar-w", icon ? "56px" : "200px");
    root.dataset.sidebar = icon ? "icon" : "expanded";
  }, [collapsed, narrow]);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const iconMode = collapsed || narrow;

  return (
    <aside className={`sidebar${iconMode ? " icon-mode" : ""}`} aria-label="主导航">
      <div className="brand" title="SmartOffice">
        <Building2 size={20} strokeWidth={2.2} />
        {!iconMode ? <span className="brand-text">SmartOffice</span> : null}
      </div>

      <Tooltip.Provider delayDuration={200}>
        {NAV_GROUPS.map((g) => {
          const items = NAV.filter((n) => n.group === g.id);
          if (!items.length) return null;
          return (
            <div className="nav-group" key={g.id}>
              {!iconMode ? <div className="nav-group-label">{g.label}</div> : null}
              {items.map((item) => {
                const Icon = item.icon;
                const link = (
                  <NavLink
                    to={item.path}
                    className={({ isActive }) => `nav-btn${isActive ? " active" : ""}`}
                    aria-label={item.label}
                  >
                    <Icon size={20} strokeWidth={2} />
                    {!iconMode ? <span className="nav-label">{item.label}</span> : null}
                  </NavLink>
                );
                if (!iconMode) return <div key={item.id}>{link}</div>;
                return (
                  <Tooltip.Root key={item.id}>
                    <Tooltip.Trigger asChild>{link}</Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content className="tooltip" side="right" sideOffset={8}>
                        {item.label}
                        <Tooltip.Arrow style={{ fill: "#0a0e13" }} />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                );
              })}
            </div>
          );
        })}
      </Tooltip.Provider>

      <div className="spacer" />
      {!narrow ? (
        <button
          type="button"
          className="nav-btn collapse-btn"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          title={collapsed ? "展开" : "收起"}
        >
          {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          {!iconMode ? <span className="nav-label">收起</span> : null}
        </button>
      ) : null}
    </aside>
  );
}
