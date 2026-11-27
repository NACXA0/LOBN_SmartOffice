import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type AuditRow, type MatchAuditRow } from "@/api/client";
import { Drawer } from "@/components/ui/Drawer";
import { Segmented, Toolbar } from "@/components/ui/Toolbar";
import { useToast } from "@/components/ui/Toast";

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

const SOURCE_LABEL: Record<string, string> = {
  face_match: "刷脸",
  schedule: "预约",
  staff_manual: "手动",
};

export function AuditPage() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const result = params.get("result") || "all";
  const source = params.get("source") || "all";
  const tab = params.get("tab") || "ledger";

  const [q, setQ] = useState("");
  const [items, setItems] = useState<AuditRow[]>([]);
  const [alerts, setAlerts] = useState<{ id: number; kind: string; title: string; space_id: string; created_at: number }[]>([]);
  const [strangers, setStrangers] = useState<(MatchAuditRow & { bucket: string })[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<AuditRow | null>(null);
  const [matchHint, setMatchHint] = useState<MatchAuditRow | null>(null);
  const [aiOk, setAiOk] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      api.aiStatus().then((s) => setAiOk(!!s.configured)).catch(() => undefined);
      if (tab === "alerts") {
        const a = await api.listAlerts(false);
        setAlerts(a.items || []);
      } else if (tab === "strangers") {
        const s = await api.strangers(60);
        setStrangers(s.items || []);
      } else {
        const res = result === "all" ? "" : result;
        const src = source === "all" ? "" : source;
        const a = await api.audit(res, 100, src);
        let list = a.items || [];
        if (q.trim()) {
          const needle = q.trim().toLowerCase();
          list = list.filter(
            (r) =>
              (r.user_id || "").toLowerCase().includes(needle) ||
              (r.display_name || "").toLowerCase().includes(needle) ||
              (r.command_id || "").toLowerCase().includes(needle) ||
              (r.door || "").toLowerCase().includes(needle),
          );
        }
        setItems(list);
      }
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }, [result, source, q, toast, tab]);

  useEffect(() => {
    const t = window.setTimeout(load, 120);
    return () => window.clearTimeout(t);
  }, [load]);

  const setFilter = (key: "result" | "source", v: string) => {
    const next = new URLSearchParams(params);
    if (!v || v === "all") next.delete(key);
    else next.set(key, v);
    setParams(next, { replace: true });
  };

  const openRow = async (row: AuditRow) => {
    setSelected(row);
    setMatchHint(null);
    if (row.source === "face_match" && row.user_id) {
      try {
        const m = await api.matchAudit(row.user_id, "", 5);
        const near = (m.items || []).find((x) => Math.abs(x.created_at - row.created_at) < 120);
        setMatchHint(near || m.items?.[0] || null);
      } catch {
        /* ignore */
      }
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>记录</h1>
          <p>放行流水与告警 · 助理在右下角</p>
        </div>
      </div>

      <Toolbar q={q} onQ={setQ} placeholder="人员 / 门 / command_id" onRefresh={load} refreshing={loading}>
        <Segmented
          value={tab}
          onChange={(v) => {
            const next = new URLSearchParams(params);
            if (v === "ledger") next.delete("tab");
            else next.set("tab", v);
            setParams(next, { replace: true });
          }}
          options={[
            { value: "ledger", label: "放行" },
            { value: "alerts", label: "告警" },
            { value: "strangers", label: "门口结果" },
          ]}
        />
        {tab === "ledger" && (
          <>
            <Segmented
              value={result}
              onChange={(v) => setFilter("result", v)}
              options={[
                { value: "all", label: "全部" },
                { value: "grant", label: "放行" },
                { value: "drop", label: "丢弃" },
              ]}
            />
            <Segmented
              value={source}
              onChange={(v) => setFilter("source", v)}
              options={[
                { value: "all", label: "来源" },
                { value: "face_match", label: "刷脸" },
                { value: "staff_manual", label: "手动" },
                { value: "schedule", label: "预约" },
              ]}
            />
          </>
        )}
      </Toolbar>

      {tab === "alerts" ? (
        <div className="card-list">
          {alerts.length === 0 ? (
            <p className="muted">{loading ? "加载中…" : "无待处理告警"}</p>
          ) : (
            alerts.map((a) => (
              <div key={a.id} className="space-card">
                <div className="space-card-body">
                  <div className="space-card-title">
                    {a.kind}: {a.title}
                  </div>
                  <div className="muted">
                    {a.space_id} · {fmtTime(a.created_at)}
                  </div>
                </div>
                <div className="row-gap">
                  {aiOk && (
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={async () => {
                        try {
                          const r = await api.vlmAlert(a.id);
                          toast.push(r.text || r.reason || "完成");
                        } catch (e) {
                          toast.push(String(e instanceof Error ? e.message : e));
                        }
                      }}
                    >
                      解释画面
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn"
                    onClick={async () => {
                      await api.ackAlert(a.id);
                      load();
                    }}
                  >
                    确认
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      ) : tab === "strangers" ? (
        <div className="card-list">
          {strangers.length === 0 ? (
            <p className="muted">{loading ? "加载中…" : "暂无门口结果"}</p>
          ) : (
            strangers.map((r) => (
              <div key={r.id} className="space-card">
                <div className="space-card-body">
                  <div className="space-card-title">
                    {r.bucket === "known" ? "熟人" : r.bucket === "stranger" ? "陌生人" : "看不清"}
                  </div>
                  <div className="muted">
                    {r.user_id || "—"} · {r.camera} · {fmtTime(r.created_at)}
                  </div>
                </div>
                <div className="row-gap">
                  {r.bucket === "stranger" && (
                    <Link className="btn ghost" to="/people">
                      录入
                    </Link>
                  )}
                  {r.bucket === "stranger" && (
                    <Link className="btn primary" to="/spaces">
                      去开门
                    </Link>
                  )}
                  {aiOk && (
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={async () => {
                        try {
                          const r2 = await api.explainCrop(r.id, "match");
                          toast.push(r2.text || r2.reason || "完成");
                        } catch (e) {
                          toast.push(String(e instanceof Error ? e.message : e));
                        }
                      }}
                    >
                      解释
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>来源</th>
              <th>人员</th>
              <th>门</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  {loading ? "加载中…" : "暂无流水"}
                </td>
              </tr>
            ) : (
              items.map((r) => (
                <tr key={r.id} className="click-row" onClick={() => openRow(r)}>
                  <td className="muted">{fmtTime(r.created_at)}</td>
                  <td>{SOURCE_LABEL[r.source] || r.source}</td>
                  <td>
                    <span className="strong">{r.display_name || r.user_id || "—"}</span>
                    {r.user_id ? <div className="sub mono">{r.user_id}</div> : null}
                  </td>
                  <td className="mono">{r.door}</td>
                  <td className={`dec ${r.result}`}>{r.result}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      )}

      <Drawer open={!!selected} onOpenChange={(o) => !o && setSelected(null)} title="开门记录">
        {selected ? (
          <>
            <div className="drawer-meta">
              <span className={`dec ${selected.result}`}>{selected.result}</span>
              <span className="note">{SOURCE_LABEL[selected.source] || selected.source}</span>
            </div>
            <dl className="kv">
              <dt>人员</dt>
              <dd>
                {selected.user_id ? (
                  <Link className="linkish" to={`/people/${selected.user_id}`}>
                    {selected.display_name || selected.user_id}
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
              <dt>门</dt>
              <dd className="mono">{selected.door}</dd>
              <dt>原因</dt>
              <dd className="mono">{selected.reason}</dd>
              <dt>command_id</dt>
              <dd className="mono">{selected.command_id || "—"}</dd>
              <dt>时间</dt>
              <dd>{fmtTime(selected.created_at)}</dd>
            </dl>
            {matchHint ? (
              <div className="card soft" style={{ marginTop: 14 }}>
                <h4 className="card-title">比对明细</h4>
                <p className="note">
                  相似度 {matchHint.similarity.toFixed(3)} · {matchHint.decision} · 摄像头{" "}
                  <span className="mono">{matchHint.camera}</span>
                </p>
                {matchHint.detail?.reason ? (
                  <p className="note mono">reason {String(matchHint.detail.reason)}</p>
                ) : null}
              </div>
            ) : null}
          </>
        ) : null}
      </Drawer>
    </div>
  );
}
