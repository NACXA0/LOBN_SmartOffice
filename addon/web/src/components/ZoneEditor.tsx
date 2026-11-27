import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Eraser, Pencil, Undo2, X } from "lucide-react";

export type Point = [number, number];

export type RegionKind = "zone" | "motion_mask" | "object_mask";

export type Region = {
  id: string;
  name: string;
  points: Point[];
};

const KIND_COLOR: Record<RegionKind, string> = {
  zone: "#3b82f6",
  motion_mask: "#f59e0b",
  object_mask: "#ef4444",
};

type Props = {
  src: string;
  kind: RegionKind;
  regions: Region[];
  activeId: string | null;
  editing: boolean;
  onEditingChange: (v: boolean) => void;
  onChange: (regions: Region[]) => void;
  onSave: (regions: Region[]) => Promise<void> | void;
};

function eventToNorm(
  e: React.PointerEvent,
  wrap: HTMLElement,
  naturalW: number,
  naturalH: number,
): Point | null {
  if (!naturalW || !naturalH) return null;
  const rect = wrap.getBoundingClientRect();
  const scale = Math.min(rect.width / naturalW, rect.height / naturalH);
  const dispW = naturalW * scale;
  const dispH = naturalH * scale;
  const ox = (rect.width - dispW) / 2;
  const oy = (rect.height - dispH) / 2;
  const x = (e.clientX - rect.left - ox) / dispW;
  const y = (e.clientY - rect.top - oy) / dispH;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
}

function toSvgPts(poly: Point[], nw: number, nh: number, rw: number, rh: number): string {
  if (!nw || !nh || !poly.length) return "";
  const scale = Math.min(rw / nw, rh / nh);
  const dispW = nw * scale;
  const dispH = nh * scale;
  const ox = (rw - dispW) / 2;
  const oy = (rh - dispH) / 2;
  return poly.map(([x, y]) => `${ox + x * dispW},${oy + y * dispH}`).join(" ");
}

export function ZoneEditor({
  src,
  kind,
  regions,
  activeId,
  editing,
  onEditingChange,
  onChange,
  onSave,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [size, setSize] = useState({ rw: 0, rh: 0, nw: 0, nh: 0 });
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const color = KIND_COLOR[kind];

  const active = regions.find((r) => r.id === activeId) || null;
  const draft = active?.points || [];

  const measure = useCallback(() => {
    const wrap = wrapRef.current;
    const img = imgRef.current;
    if (!wrap || !img) return;
    setSize({
      rw: wrap.clientWidth,
      rh: wrap.clientHeight,
      nw: img.naturalWidth,
      nh: img.naturalHeight,
    });
  }, []);

  useEffect(() => {
    measure();
    const ro = new ResizeObserver(measure);
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, [measure, src]);

  function updateActivePoints(points: Point[]) {
    if (!activeId) return;
    onChange(regions.map((r) => (r.id === activeId ? { ...r, points } : r)));
  }

  function hitHandle(e: React.PointerEvent): number | null {
    if (!active || !size.nw) return null;
    const wrap = wrapRef.current;
    if (!wrap) return null;
    const scale = Math.min(size.rw / size.nw, size.rh / size.nh);
    const dispW = size.nw * scale;
    const dispH = size.nh * scale;
    const ox = (size.rw - dispW) / 2;
    const oy = (size.rh - dispH) / 2;
    const rect = wrap.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    for (let i = 0; i < draft.length; i++) {
      const [x, y] = draft[i];
      if (Math.hypot(px - (ox + x * dispW), py - (oy + y * dispH)) <= 14) return i;
    }
    return null;
  }

  function onPointerDown(e: React.PointerEvent) {
    if (!editing || !activeId) return;
    const wrap = wrapRef.current;
    if (!wrap) return;
    const hit = hitHandle(e);
    if (hit != null) {
      setDragIdx(hit);
      return;
    }
    const p = eventToNorm(e, wrap, size.nw, size.nh);
    if (!p) return;
    if (draft.length >= 3) {
      const [fx, fy] = draft[0];
      if (Math.hypot(p[0] - fx, p[1] - fy) < 0.04) return;
    }
    updateActivePoints([...draft, p]);
  }

  function onPointerMove(e: React.PointerEvent) {
    if (dragIdx == null || !editing) return;
    const wrap = wrapRef.current;
    if (!wrap) return;
    const p = eventToNorm(e, wrap, size.nw, size.nh);
    if (!p) return;
    updateActivePoints(draft.map((pt, i) => (i === dragIdx ? p : pt)));
  }

  async function save() {
    if (active && active.points.length > 0 && active.points.length < 3) return;
    setSaving(true);
    try {
      await onSave(regions);
      onEditingChange(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`zone-editor${editing ? " is-editing" : ""}`}>
      <div
        ref={wrapRef}
        className="zone-canvas"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragIdx(null)}
        onPointerCancel={() => setDragIdx(null)}
      >
        <img ref={imgRef} src={src} alt="" onLoad={measure} draggable={false} />
        <svg className="zone-svg" width={size.rw} height={size.rh}>
          {regions.map((r) => {
            const pts = toSvgPts(r.points || [], size.nw, size.nh, size.rw, size.rh);
            if (!pts) return null;
            const activeNow = r.id === activeId;
            return (
              <polygon
                key={r.id}
                points={pts}
                style={{
                  fill: activeNow ? `${color}44` : `${color}22`,
                  stroke: color,
                  strokeWidth: activeNow ? 2.5 : 1.5,
                  strokeDasharray: (r.points?.length || 0) < 3 ? "6 4" : undefined,
                }}
              />
            );
          })}
          {editing &&
            draft.map(([x, y], i) => {
              if (!size.nw) return null;
              const scale = Math.min(size.rw / size.nw, size.rh / size.nh);
              const dispW = size.nw * scale;
              const dispH = size.nh * scale;
              const ox = (size.rw - dispW) / 2;
              const oy = (size.rh - dispH) / 2;
              return (
                <circle
                  key={i}
                  cx={ox + x * dispW}
                  cy={oy + y * dispH}
                  r={7}
                  className={i === 0 ? "zone-handle first" : "zone-handle"}
                  style={{ fill: i === 0 ? color : "#fff", stroke: color }}
                />
              );
            })}
        </svg>
        {editing && (
          <div className="zone-hint">
            {!activeId
              ? "先选一个区域再画"
              : draft.length === 0
                ? "在画面上点选顶点（可遮 OSD）"
                : draft.length < 3
                  ? `已选 ${draft.length} 点 · 至少 3 点`
                  : "拖动顶点调整 · 点保存"}
          </div>
        )}
      </div>

      <div className="zone-toolbar">
        {!editing ? (
          <button
            type="button"
            className="btn ghost"
            disabled={!activeId}
            onClick={() => onEditingChange(true)}
          >
            <Pencil size={16} /> 在画面上编辑
          </button>
        ) : (
          <>
            <button
              type="button"
              className="icon-btn"
              title="撤销一点"
              onClick={() => updateActivePoints(draft.slice(0, -1))}
              disabled={!draft.length}
            >
              <Undo2 size={18} />
            </button>
            <button
              type="button"
              className="icon-btn"
              title="清空当前"
              onClick={() => updateActivePoints([])}
              disabled={!draft.length}
            >
              <Eraser size={18} />
            </button>
            <button type="button" className="icon-btn" title="取消" onClick={() => onEditingChange(false)}>
              <X size={18} />
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={saving || (draft.length > 0 && draft.length < 3)}
              onClick={save}
            >
              <Check size={16} /> 保存
            </button>
          </>
        )}
      </div>
    </div>
  );
}
