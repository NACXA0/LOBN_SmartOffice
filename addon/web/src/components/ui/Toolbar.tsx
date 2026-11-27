import { RefreshCw, Search } from "lucide-react";
import type { ReactNode } from "react";

export function Toolbar({
  q,
  onQ,
  placeholder = "检索…",
  onRefresh,
  refreshing,
  children,
}: {
  q: string;
  onQ: (v: string) => void;
  placeholder?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <div className="search-wrap">
        <Search size={14} className="search-ico" aria-hidden />
        <input
          className="input search-input"
          type="search"
          value={q}
          placeholder={placeholder}
          onChange={(e) => onQ(e.target.value)}
        />
      </div>
      {children}
      {onRefresh ? (
        <button type="button" className="btn ghost" disabled={refreshing} onClick={onRefresh}>
          <RefreshCw size={16} className={refreshing ? "spin" : undefined} /> 刷新
        </button>
      ) : null}
    </div>
  );
}

export function Segmented({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          className={`seg-btn${value === o.value ? " active" : ""}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
