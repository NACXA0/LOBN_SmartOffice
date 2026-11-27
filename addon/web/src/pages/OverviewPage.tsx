import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, DoorOpen, MapPinned, RefreshCw, Shield } from "lucide-react";
import { api, type Dashboard } from "@/api/client";
import { STATUS_LABEL } from "@/lib/status";
import { useToast } from "@/components/ui/Toast";

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="bar-val">{value}</span>
    </div>
  );
}

function fmtTime(ts: number) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

export function OverviewPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [d, setD] = useState<Dashboard | null>(null);

  const load = useCallback(async () => {
    try {
      setD(await api.stats());
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    }
  }, [toast]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 20000);
    return () => window.clearInterval(t);
  }, [load]);

  const by = d?.persons.by_status || {};
  const statusMax = Math.max(1, ...Object.values(by));
  const h24 = d?.access.h24 || { grant: 0, deny: 0, skip: 0, by_source: {} };
  const bySource = h24.by_source || {};
  const sourceMax = Math.max(1, ...Object.values(bySource), h24.grant || 1);
  const pending = d?.persons.pending_recollect || [];
  const dbMb = ((d?.store.db_bytes || 0) / (1024 * 1024)).toFixed(2);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>总览</h1>
          <p>办公室现在要处理什么</p>
        </div>
        <button type="button" className="btn ghost" onClick={load}>
          <RefreshCw size={16} /> 刷新
        </button>
      </div>

      <div className="kpi-grid">
        <Link to="/audit?tab=alerts" className="kpi kpi-link warn">
          <div className="kpi-ico"><AlertTriangle size={18} /></div>
          <div>
            <div className="kpi-label">待处理告警</div>
            <div className="kpi-val">{d?.office?.open_alerts ?? "—"}</div>
            <div className="kpi-sub">陌生人 / 滞留 / 资产</div>
          </div>
        </Link>
        <Link to="/spaces" className="kpi kpi-link">
          <div className="kpi-ico"><MapPinned size={18} /></div>
          <div>
            <div className="kpi-label">有人的空间</div>
            <div className="kpi-val">{d?.office?.occupied_spaces ?? "—"}</div>
            <div className="kpi-sub">围栏内人数</div>
          </div>
        </Link>
        <Link to="/audit?result=grant" className="kpi kpi-link">
          <div className="kpi-ico"><DoorOpen size={18} /></div>
          <div>
            <div className="kpi-label">今日放行</div>
            <div className="kpi-val">{h24.grant}</div>
            <div className="kpi-sub">
              拒 {h24.deny}
              {typeof h24.drop === "number" ? ` · 丢弃 ${h24.drop}` : ""}
            </div>
          </div>
        </Link>
        <Link to="/spaces" className="kpi kpi-link">
          <div className="kpi-ico"><Shield size={18} /></div>
          <div>
            <div className="kpi-label">正在布防</div>
            <div className="kpi-val">{d?.office?.armed_spaces ?? "—"}</div>
            <div className="kpi-sub">
              {d?.overlapping_spaces?.length ? `重叠窗口 ${d.overlapping_spaces.length}` : "按时刻表"}
            </div>
          </div>
        </Link>
      </div>

      <div className="split-2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3 className="card-title">人脸状态分布</h3>
          {Object.keys(by).length === 0 ? (
            <p className="note">暂无人员</p>
          ) : (
            Object.entries(by).map(([k, v]) => (
              <Bar key={k} label={STATUS_LABEL[k] || k} value={v} max={statusMax} color="var(--accent)" />
            ))
          )}
        </div>
        <div className="card">
          <h3 className="card-title">今日放行按来源</h3>
          {Object.keys(bySource).length === 0 && !h24.grant ? (
            <p className="note">今日尚无放行</p>
          ) : Object.keys(bySource).length === 0 ? (
            <Bar label="face_match" value={h24.grant} max={sourceMax} color="var(--ok)" />
          ) : (
            Object.entries(bySource).map(([k, v]) => (
              <Bar key={k} label={k === "face_match" ? "刷脸" : k} value={v} max={sourceMax} color="var(--ok)" />
            ))
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h3 className="card-title" style={{ margin: 0 }}>待重采队列</h3>
          <button type="button" className="linkish" onClick={() => navigate("/people?status=pending")}>
            查看全部
          </button>
        </div>
        {pending.length === 0 ? (
          <p className="note">没有待重采人员</p>
        ) : (
          <ul className="mini-list">
            {pending.slice(0, 8).map((p) => (
              <li key={p.user_id}>
                <button type="button" className="linkish" onClick={() => navigate(`/people/${p.user_id}`)}>
                  {p.display_name || p.user_id}
                </button>
                <span className="note">{fmtTime(p.updated_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card soft" style={{ marginTop: 14 }}>
        <h3 className="card-title">运行时</h3>
        <div className="runtime-grid">
          <span>模型 {d?.runtime.embedder_ready ? "就绪" : "未就绪"} · {d?.runtime.model_version || "—"}</span>
          <span>MQTT {d?.runtime.mqtt_enabled ? d.runtime.mqtt_host : "关闭"}</span>
          <span>磁盘 {d?.runtime.disk_full ? "不足" : "正常"}</span>
          <span>库 {dbMb} MB · 会话 {d?.runtime.open_sessions ?? 0}</span>
        </div>
        <p className="note" style={{ marginTop: 8 }}>链路灯见底栏；健康异常时先看 MQTT / 模型 / 磁盘。</p>
      </div>
    </div>
  );
}
