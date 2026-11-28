import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import * as Switch from "@radix-ui/react-switch";
import { UserPlus } from "lucide-react";
import { api, type Person } from "@/api/client";
import { CreatePersonDrawer } from "@/components/CreatePersonDrawer";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Drawer } from "@/components/ui/Drawer";
import { Segmented, Toolbar } from "@/components/ui/Toolbar";
import { useToast } from "@/components/ui/Toast";

function fmtTime(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function kindLabel(p: Person) {
  const k = p.person_kind || "staff";
  if (k === "stranger") return "陌生人";
  if (k === "student") return "学员";
  if (k === "visitor") return "访客";
  if (k === "staff") return "员工";
  return k;
}

function originHint(p: Person) {
  if (p.person_kind === "stranger") return "监控建档";
  if (p.origin === "booking" && !p.sighted) return "仅凭证·未造访";
  if (p.origin === "booking" && p.sighted) return "预约凭证·已造访";
  if (p.sighted) return "已造访";
  return p.origin === "manual" ? "手工" : "本店";
}

export function PeoplePage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const scope = params.get("scope") || "all";
  const peek = params.get("peek");

  const [q, setQ] = useState("");
  const [items, setItems] = useState<Person[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<Person | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.listPersons(q.trim(), scope);
      setItems(r.items || []);
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }, [q, scope, toast]);

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
    const list = [...items];
    list.sort((a, b) => (b.last_seen_at || b.updated_at || 0) - (a.last_seen_at || a.updated_at || 0));
    return list;
  }, [items]);

  const setScope = (v: string) => {
    const next = new URLSearchParams(params);
    if (!v || v === "all") next.delete("scope");
    else next.set("scope", v);
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
          <p>监控建档 · 手动录入 · 相册入库 · 预约凭证与真实造访分开</p>
        </div>
        <button type="button" className="btn primary" onClick={() => setCreating(true)}>
          <UserPlus size={16} /> 新建人员
        </button>
      </div>

      <Toolbar q={q} onQ={setQ} placeholder="姓名 / user_id" onRefresh={load} refreshing={loading}>
        <Segmented
          value={scope}
          onChange={setScope}
          options={[
            { value: "all", label: "全部" },
            { value: "sighted", label: "已造访" },
            { value: "stranger", label: "陌生人" },
            { value: "credential", label: "仅凭证" },
          ]}
        />
      </Toolbar>

      <div className="table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>姓名</th>
              <th>身份</th>
              <th>造访</th>
              <th>人脸</th>
              <th>可开门</th>
              <th>最近出现</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="empty-cell">
                  {loading
                    ? "加载中…"
                    : "暂无人员 — 点「新建人员」手动录入，或等门口识别自动建档"}
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
                <tr key={p.user_id} className="click-row" onClick={() => openPeek(p)}>
                  <td className="strong">{p.display_name || "未命名"}</td>
                  <td>
                    <span className="pill">{kindLabel(p)}</span>
                    <span className="muted" style={{ marginLeft: 6, fontSize: "0.78rem" }}>
                      {originHint(p)}
                    </span>
                  </td>
                  <td className="mono">{p.visit_count ?? 0}</td>
                  <td>
                    <StatusBadge status={p.face_status} />
                  </td>
                  <td
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    {p.person_kind === "stranger" ? (
                      <span className="muted">—</span>
                    ) : (
                      <Switch.Root
                        className="switch"
                        checked={!!p.can_open}
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
                    )}
                  </td>
                  <td className="muted">{fmtTime(p.last_seen_at || p.updated_at)}</td>
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
              <span className="pill">{kindLabel(detail)}</span>
              <span className="sub mono">user_id {detail.user_id}</span>
            </div>
            <p className="note">
              {originHint(detail)} · 造访 {detail.visit_count ?? 0} 次
              {typeof detail.frame_count === "number" ? ` · 合格帧 ${detail.frame_count}` : ""}
            </p>
            <p className="note" style={{ marginTop: 10 }}>
              预约平台录入的人脸只是凭证；只有「造访」表示监控真实见过此人。陌生人可在档案里关联到正式身份。
            </p>
            <p style={{ marginTop: 12 }}>
              <Link className="linkish" to={`/people/${detail.user_id}`}>
                查看完整档案 →
              </Link>
            </p>
          </>
        ) : null}
      </Drawer>

      <CreatePersonDrawer open={creating} onOpenChange={setCreating} onCreated={load} />
    </div>
  );
}
