import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Bell,
  DoorOpen,
  Mic,
  Plus,
  RefreshCw,
  Shield,
  ShieldOff,
  Sparkles,
  Trash2,
  Volume2,
} from "lucide-react";
import { api, apiUrl, type Space } from "@/api/client";
import { ZoneEditor, type Point, type Region, type RegionKind } from "@/components/ZoneEditor";
import { useToast } from "@/components/ui/Toast";

const KIND_META: { id: RegionKind; title: string; hint: string }[] = [
  { id: "zone", title: "区域", hint: "只在这些多边形内做放行/人数判断" },
  { id: "motion_mask", title: "画面变动遮罩", hint: "遮住 OSD / 时钟等，避免误触发变动" },
  { id: "object_mask", title: "目标遮罩", hint: "忽略海报、假人等固定误检" },
];

function asRegions(raw: unknown): Region[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((r: any, i) => ({
    id: String(r?.id || `r${i + 1}`),
    name: String(r?.name || r?.id || `区域${i + 1}`),
    points: (r?.points || []) as Point[],
  }));
}

export function SpaceDetailPage() {
  const { spaceId = "" } = useParams();
  const toast = useToast();
  const [space, setSpace] = useState<Space | null>(null);
  const [note, setNote] = useState("");
  const [tick, setTick] = useState(0);
  const [aiOk, setAiOk] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [kind, setKind] = useState<RegionKind>("motion_mask");
  const [regions, setRegions] = useState<Record<RegionKind, Region[]>>({
    zone: [],
    motion_mask: [],
    object_mask: [],
  });
  const [activeId, setActiveId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [labelsCatalog, setLabelsCatalog] = useState<{ id: string; zh: string }[]>([]);
  const [labelQ, setLabelQ] = useState("");
  const [filterLabel, setFilterLabel] = useState<string>("person");
  const recording = useRef<MediaRecorder | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await api.spaceDetail(spaceId);
      setSpace(s);
      setRegions({
        zone: asRegions(s.zones),
        motion_mask: asRegions(s.motion_masks),
        object_mask: asRegions(s.object_masks),
      });
      const st = await api.aiStatus();
      setAiOk(!!st.configured);
      const lb = await api.visionLabels();
      const cat =
        lb.catalog ||
        (lb.items || []).map((id) => ({ id, zh: lb.zh?.[id] || id }));
      setLabelsCatalog(cat);
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    }
  }, [spaceId, toast]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (editing) return;
    const t = window.setInterval(() => setTick((x) => x + 1), 4000);
    return () => window.clearInterval(t);
  }, [editing]);

  useEffect(() => {
    const list = regions[kind];
    if (!list.length) {
      setActiveId(null);
      return;
    }
    if (!activeId || !list.some((r) => r.id === activeId)) {
      setActiveId(list[0].id);
    }
  }, [kind, regions, activeId]);

  const preview = space?.camera
    ? `${apiUrl(`/api/spaces/${encodeURIComponent(spaceId)}/preview.jpg`)}?t=${tick}`
    : "";
  const canOpen = space?.kind === "door" || !!space?.door_node;
  const motion = space?.motion_cfg || {};
  const track = space?.track_cfg || { labels: [], filters: {} };
  const audio = space?.audio_cfg || { enabled: false };
  const selectedLabels: string[] = track.labels || [];

  const labelZh = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of labelsCatalog) m[c.id] = c.zh || c.id;
    return m;
  }, [labelsCatalog]);

  const filteredLabels = useMemo(() => {
    const q = labelQ.trim().toLowerCase();
    return (labelsCatalog || [])
      .filter((l) => !q || l.id.toLowerCase().includes(q) || (l.zh || "").toLowerCase().includes(q))
      .slice(0, 80);
  }, [labelsCatalog, labelQ]);

  const activeFilter = (track.filters || {})[filterLabel] || { min_score: 0.5, min_area: 0.002 };

  async function persistRegions(next: Record<RegionKind, Region[]>) {
    await api.setRegions(spaceId, {
      zones: next.zone,
      motion_masks: next.motion_mask,
      object_masks: next.object_mask,
    });
    await load();
  }

  function addRegion() {
    const id = `${kind}_${Date.now().toString(36)}`;
    const name =
      kind === "zone" ? `区域${regions.zone.length + 1}` : kind === "motion_mask" ? `变动遮罩${regions.motion_mask.length + 1}` : `目标遮罩${regions.object_mask.length + 1}`;
    const item: Region = { id, name, points: [] };
    const next = { ...regions, [kind]: [...regions[kind], item] };
    setRegions(next);
    setActiveId(id);
    setEditing(true);
  }

  async function removeRegion(id: string) {
    const next = { ...regions, [kind]: regions[kind].filter((r) => r.id !== id) };
    setRegions(next);
    await persistRegions(next);
    toast.push("已删除");
  }

  async function saveRegions(list: Region[]) {
    const next = { ...regions, [kind]: list };
    setRegions(next);
    await persistRegions(next);
    toast.push("遮罩/区域已保存");
  }

  async function patchMotion(partial: Record<string, unknown>) {
    const motion_cfg = { ...motion, ...partial };
    setSpace(await api.patchVision(spaceId, { motion_cfg }));
  }

  async function patchAudio(partial: Record<string, unknown>) {
    setSpace(await api.patchVision(spaceId, { audio_cfg: { ...audio, ...partial } }));
  }

  async function toggleLabel(label: string) {
    const set = new Set(selectedLabels);
    if (set.has(label)) set.delete(label);
    else set.add(label);
    const next = Array.from(set);
    if (!next.includes(filterLabel) && next.length) setFilterLabel(next[0]);
    setSpace(
      await api.patchVision(spaceId, {
        track_cfg: { ...track, labels: next },
      }),
    );
  }

  async function patchFilter(partial: { min_score?: number; min_area?: number }) {
    const filters = { ...(track.filters || {}) };
    filters[filterLabel] = { ...(filters[filterLabel] || {}), ...partial };
    setSpace(await api.patchVision(spaceId, { track_cfg: { ...track, filters } }));
  }

  async function openDoor() {
    try {
      const r = await api.manualOpen(spaceId, note);
      toast.push(r.ok ? "已申请开门" : `未开门：${r.reason}`);
      if (r.ok) setNote("");
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    }
  }

  async function toggleArm() {
    if (!space) return;
    try {
      await api.setArm(spaceId, { override: !space.armed });
      await load();
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    }
  }

  async function explainFrame() {
    if (!aiOk || aiBusy) return;
    setAiBusy(true);
    setAiText("");
    try {
      const r = await api.explainSpace(spaceId);
      setAiText(r.text || r.reason || "");
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setAiBusy(false);
    }
  }

  async function holdTalk(start: boolean) {
    if (!aiOk) return;
    if (start) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const rec = new MediaRecorder(stream);
        const chunks: BlobPart[] = [];
        rec.ondataavailable = (ev) => chunks.push(ev.data);
        rec.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          try {
            const r = await api.transcribe(new Blob(chunks, { type: "audio/webm" }));
            if (r.text) setNote((n) => (n ? `${n} ${r.text}` : r.text!));
          } catch (e) {
            toast.push(String(e instanceof Error ? e.message : e));
          }
        };
        recording.current = rec;
        rec.start();
      } catch (e) {
        toast.push(String(e instanceof Error ? e.message : e));
      }
    } else if (recording.current) {
      recording.current.stop();
      recording.current = null;
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link to="/spaces" className="muted">
            ← 空间
          </Link>
          <h1>{space?.name || spaceId}</h1>
          <div className="space-status-row">
            <span className={`pill${space?.armed ? " warn" : ""}`}>{space?.armed ? "布防" : "撤防"}</span>
            <span className="pill">人≈{Number(space?.person_count || 0).toFixed(1)}</span>
            <span className="pill muted-pill">{space?.kind}</span>
          </div>
        </div>
        <div className="row-gap">
          {aiOk && preview && (
            <button type="button" className="btn ghost" disabled={aiBusy} onClick={explainFrame}>
              <Sparkles size={16} /> {aiBusy ? "…" : "看这一帧"}
            </button>
          )}
          <button type="button" className="btn ghost" onClick={load} disabled={editing}>
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {preview ? (
        <ZoneEditor
          src={preview}
          kind={kind}
          regions={regions[kind]}
          activeId={activeId}
          editing={editing}
          onEditingChange={setEditing}
          onChange={(list) => setRegions((r) => ({ ...r, [kind]: list }))}
          onSave={saveRegions}
        />
      ) : (
        <p className="muted">未配置摄像头</p>
      )}

      {aiText && (
        <div className="ai-bubble">
          <Sparkles size={16} />
          <p>{aiText}</p>
        </div>
      )}

      <div className="action-strip">
        {canOpen && (
          <button type="button" className="action-tile primary" onClick={openDoor}>
            <DoorOpen size={22} />
            <span>开门</span>
          </button>
        )}
        <button type="button" className="action-tile" onClick={toggleArm}>
          {space?.armed ? <ShieldOff size={22} /> : <Shield size={22} />}
          <span>{space?.armed ? "撤防" : "布防"}</span>
        </button>
        {!!space?.alerts?.length && (
          <Link to="/audit?tab=alerts" className="action-tile warn">
            <Bell size={22} />
            <span>{space.alerts.length} 告警</span>
          </Link>
        )}
      </div>

      {canOpen && (
        <div className="note-chip-row">
          {note ? <span className="note-chip">{note}</span> : <span className="muted">开门备注（可选）</span>}
          {aiOk ? (
            <button
              type="button"
              className="icon-btn"
              title="按住说话"
              onMouseDown={() => holdTalk(true)}
              onMouseUp={() => holdTalk(false)}
              onTouchStart={() => holdTalk(true)}
              onTouchEnd={() => holdTalk(false)}
            >
              <Mic size={18} />
            </button>
          ) : null}
        </div>
      )}

      {/* Frigate 风格：遮罩 / 区域 */}
      <div className="panel">
        <h3>遮罩 / 区域</h3>
        <p className="muted">画面有 OSD 时必须加「画面变动遮罩」，否则时钟/水印会一直触发。</p>
        <div className="seg-row">
          {KIND_META.map((k) => (
            <button
              key={k.id}
              type="button"
              className={`seg-btn${kind === k.id ? " active" : ""}`}
              onClick={() => {
                setEditing(false);
                setKind(k.id);
              }}
            >
              {k.title}
              <span className="seg-count">{regions[k.id].length}</span>
            </button>
          ))}
        </div>
        <p className="muted">{KIND_META.find((k) => k.id === kind)?.hint}</p>
        <div className="region-list">
          {regions[kind].map((r) => (
            <button
              key={r.id}
              type="button"
              className={`region-row${activeId === r.id ? " active" : ""}`}
              onClick={() => setActiveId(r.id)}
            >
              <span>
                {r.name}
                <span className="muted"> · {r.points?.length || 0} 点</span>
              </span>
              <span
                className="icon-btn"
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  removeRegion(r.id);
                }}
              >
                <Trash2 size={16} />
              </span>
            </button>
          ))}
          <button type="button" className="region-row add" onClick={addRegion}>
            <Plus size={16} /> 添加
          </button>
        </div>
      </div>

      {/* 画面变动检测 */}
      <div className="panel">
        <div className="panel-head-row">
          <h3>画面变动检测</h3>
          <label className="switch">
            <input
              type="checkbox"
              checked={!!motion.enabled}
              onChange={(e) => patchMotion({ enabled: e.target.checked })}
            />
            <span>开启</span>
          </label>
        </div>
        <label className="slider-field">
          <span>画面变动阈值 · {Number(motion.threshold ?? 30)}</span>
          <input
            type="range"
            min={1}
            max={255}
            value={Number(motion.threshold ?? 30)}
            onChange={(e) => patchMotion({ threshold: Number(e.target.value) })}
          />
        </label>
        <label className="slider-field">
          <span>轮廓区域 · {Number(motion.contour_area ?? 10)}</span>
          <input
            type="range"
            min={1}
            max={500}
            value={Number(motion.contour_area ?? 10)}
            onChange={(e) => patchMotion({ contour_area: Number(e.target.value) })}
          />
        </label>
        <label className="switch">
          <input
            type="checkbox"
            checked={!!motion.improve_contrast}
            onChange={(e) => patchMotion({ improve_contrast: e.target.checked })}
          />
          <span>改善对比度</span>
        </label>
        <label className="slider-field">
          <span>闪电阈值 · {Number(motion.lightning_threshold ?? 0.8)}</span>
          <input
            type="range"
            min={30}
            max={100}
            value={Math.round(Number(motion.lightning_threshold ?? 0.8) * 100)}
            onChange={(e) => patchMotion({ lightning_threshold: Number(e.target.value) / 100 })}
          />
        </label>
        <label className="slider-field">
          <span>
            跳过画面变动阈值 · {Number(motion.frame_skip_threshold ?? 0) || "关"}
          </span>
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(Number(motion.frame_skip_threshold ?? 0) * 100)}
            onChange={(e) => {
              const v = Number(e.target.value) / 100;
              patchMotion({ frame_skip_threshold: v <= 0 ? 0 : v });
            }}
          />
        </label>
        <label className="slider-field">
          <span>变化量权重 · {Number(motion.delta_alpha ?? 0.2)}</span>
          <input
            type="range"
            min={1}
            max={100}
            value={Math.round(Number(motion.delta_alpha ?? 0.2) * 100)}
            onChange={(e) => patchMotion({ delta_alpha: Number(e.target.value) / 100 })}
          />
        </label>
        <label className="slider-field">
          <span>背景更新速度 · {Number(motion.bg_alpha ?? 0.05)}</span>
          <input
            type="range"
            min={1}
            max={50}
            value={Math.round(Number(motion.bg_alpha ?? 0.05) * 100)}
            onChange={(e) => patchMotion({ bg_alpha: Number(e.target.value) / 100 })}
          />
        </label>
      </div>

      {/* 追踪目标 */}
      <div className="panel">
        <h3>要追踪的目标</h3>
        <p className="muted">已选 {selectedLabels.length} 个 · 与 Frigate/YOLO 标签对齐</p>
        <div className="chip-list" style={{ marginBottom: 10 }}>
          {selectedLabels.map((l) => (
            <button key={l} type="button" className="info-chip clickable" onClick={() => toggleLabel(l)}>
              {labelZh[l] || l} ×
            </button>
          ))}
        </div>
        <input
          value={labelQ}
          onChange={(e) => setLabelQ(e.target.value)}
          placeholder="搜索…"
          style={{ marginBottom: 8 }}
        />
        <div className="label-grid">
          {filteredLabels.map((l) => (
            <button
              key={l.id}
              type="button"
              className={`label-chip${selectedLabels.includes(l.id) ? " on" : ""}`}
              onClick={() => toggleLabel(l.id)}
            >
              {l.zh || l.id}
            </button>
          ))}
        </div>
      </div>

      {/* 目标过滤器 */}
      <div className="panel">
        <h3>目标过滤器</h3>
        <p className="muted">按置信度 / 面积减少误报（对齐 Frigate object filters）。</p>
        {selectedLabels.length === 0 ? (
          <p className="muted">先勾选要追踪的目标</p>
        ) : (
          <>
            <div className="chip-list" style={{ marginBottom: 10 }}>
              {selectedLabels.map((l) => (
                <button
                  key={l}
                  type="button"
                  className={`info-chip clickable${filterLabel === l ? " on" : ""}`}
                  onClick={() => setFilterLabel(l)}
                >
                  {labelZh[l] || l}
                </button>
              ))}
            </div>
            <label className="slider-field">
              <span>
                {labelZh[filterLabel] || filterLabel} · 最低置信度 ·{" "}
                {Number(activeFilter.min_score ?? 0.5).toFixed(2)}
              </span>
              <input
                type="range"
                min={5}
                max={95}
                value={Math.round(Number(activeFilter.min_score ?? 0.5) * 100)}
                onChange={(e) => patchFilter({ min_score: Number(e.target.value) / 100 })}
              />
            </label>
            <label className="slider-field">
              <span>
                最小面积 · {Number(activeFilter.min_area ?? 0.002).toFixed(3)}
              </span>
              <input
                type="range"
                min={1}
                max={200}
                value={Math.round(Number(activeFilter.min_area ?? 0.002) * 1000)}
                onChange={(e) => patchFilter({ min_area: Number(e.target.value) / 1000 })}
              />
            </label>
          </>
        )}
      </div>

      {/* 音频 */}
      <div className="panel">
        <div className="panel-head-row">
          <h3>
            <Volume2 size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
            音频检测
          </h3>
          <label className="switch">
            <input
              type="checkbox"
              checked={!!audio.enabled}
              onChange={(e) => patchAudio({ enabled: e.target.checked })}
            />
            <span>开启</span>
          </label>
        </div>
        <p className="muted">开启后按 RMS 能量告警（需上游供音频帧；本机单测用合成波形）。</p>
        <label className="slider-field">
          <span>最小 RMS · {Number(audio.min_rms ?? 0.02)}</span>
          <input
            type="range"
            min={1}
            max={50}
            value={Math.round(Number(audio.min_rms ?? 0.02) * 100)}
            onChange={(e) => patchAudio({ min_rms: Number(e.target.value) / 100 })}
          />
        </label>
      </div>
    </div>
  );
}
