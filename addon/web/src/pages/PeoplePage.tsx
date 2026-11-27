import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import * as Switch from "@radix-ui/react-switch";
import { api, type Person } from "@/api/client";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Drawer } from "@/components/ui/Drawer";
import { Segmented, Toolbar } from "@/components/ui/Toolbar";
import { useToast } from "@/components/ui/Toast";

function fmtTime(ts?: number) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function matchStatus(p: Person, status: string) {
  if (!status || status === "all") return true;
  if (status === "accepted") {
    return !!p.enabled && (p.face_status === "accepted" || p.face_status === "verified");
  }
  if (status === "pending") return p.face_status === "pending";
  if (status === "disabled") return !p.enabled || p.face_status === "rejected";
  return p.face_status === status;
}

export function PeoplePage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "all";
  const peek = params.get("peek");

  const [q, setQ] = useState("");
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<Person | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.listPersons(q.trim());
      setItems(r.items || []);
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }, [q, toast]);

  useEffect(() => {
    const t = window.setTimeout(load, 160);
    return () => window.clearTimeout(t);
  }, [load]);

  useEffect(() => {
    if (!peek) return;
    const hit = items.find((p) => p.user_id === peek);
    if (hit) setDetail(hit);
  }, [peek, items]);

  const filtered = useMemo(() => {
    const list = items.filter((p) => matchStatus(p, status));
    list.sort((a, b) => (a.face_status === "pending" ? 0 : 1) - (b.face_status === "pending" ? 0 : 1));
    return list;
  }, [items, status]);

  const setStatus = (v: string) => {
    const next = new URLSearchParams(params);
    if (!v || v === "all") next.delete("status");
    else next.set("status", v);
    setParams(next, { replace: true });
  };

  const openPeek = (p: Person) => {
    setDetail(p);
    const next = new URLSearchParams(params);
    next.set("peek", p.user_id);
    setParams(next, { replace: true });
  };

  const closePeek = () => {
    setDetail(null);
    const next = new URLSearchParams(params);
    next.delete("peek");
    setParams(next, { replace: true });
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>人员</h1>
          <p>本店人员档案 · 人脸是凭证 · 启停只影响刷脸开门</p>
        </div>
      </div>

      <Toolbar q={q} onQ={setQ} placeholder="姓名 / user_id" onRefresh={load} refreshing={loading}>
        <Segmented
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "全部" },
            { value: "pending", label: "待重采" },
            { value: "accepted", label: "可开门" },
            { value: "disabled", label: "已停用" },
          ]}
        />
      </Toolbar>

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>姓名</th>
              <th>user_id</th>
              <th>人脸</th>
              <th>可开门</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  {loading ? "加载中…" : "暂无人员 — 可在档案页采集，或从小程序录入"}
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
                <tr key={p.user_id} className="click-row" onClick={() => openPeek(p)}>
                  <td className="strong">{p.display_name || "未命名"}</td>
                  <td className="mono">{p.user_id}</td>
                  <td>
                    <StatusBadge status={p.face_status} />
                  </td>
                  <td
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    <Switch.Root
                      className="switch"
                      checked={!!p.enabled && p.face_status !== "rejected"}
                      onCheckedChange={async (on) => {
                        try {
                          if (on) await api.enablePerson(p.user_id);
                          else await api.disablePerson(p.user_id);
                          toast.push(on ? "已启用" : "已停用");
                          load();
                        } catch {
                          toast.push("操作失败");
                        }
                      }}
                      aria-label="可开门"
                    >
                      <Switch.Thumb className="switch-thumb" />
                    </Switch.Root>
                  </td>
                  <td className="muted">{fmtTime(p.updated_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Drawer
        open={!!detail}
        onOpenChange={(o) => !o && closePeek()}
        title={detail?.display_name || detail?.user_id || "人员"}
        footer={
          detail ? (
            <>
              <button type="button" className="btn" onClick={() => navigate(`/people/${detail.user_id}`)}>
                打开档案
              </button>
              <button
                type="button"
                className="btn primary"
                onClick={() => navigate(`/people/${detail.user_id}/capture`)}
              >
                采集
              </button>
            </>
          ) : null
        }
      >
        {detail ? (
          <>
            <div className="drawer-meta">
              <StatusBadge status={detail.face_status} />
              <span className="sub mono">user_id {detail.user_id}</span>
            </div>
            <p className="note">
              验证 {detail.verify_ok_count ?? 0}/3 · 连续失败 {detail.verify_fail_streak ?? 0}
              {typeof detail.frame_count === "number" ? ` · 合格帧 ${detail.frame_count}` : ""}
            </p>
            <p className="note" style={{ marginTop: 10 }}>
              启停只影响刷脸；预约到点开门不依赖人脸。删除请进入档案。
            </p>
            <p style={{ marginTop: 12 }}>
              <Link className="linkish" to={`/people/${detail.user_id}`}>
                查看完整档案 →
              </Link>
            </p>
          </>
        ) : null}
      </Drawer>
    </div>
  );
}
