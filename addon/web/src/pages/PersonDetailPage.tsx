import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as Switch from "@radix-ui/react-switch";
import { ArrowLeft, Camera } from "lucide-react";
import { api, type MatchAuditRow, type PersonDetail } from "@/api/client";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

export function PersonDetailPage() {
  const { userId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [detail, setDetail] = useState<PersonDetail | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [matches, setMatches] = useState<MatchAuditRow[]>([]);
  const [pendingDelete, setPendingDelete] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const d = await api.personDetail(userId);
      setDetail(d);
      setNameDraft(d.display_name || "");
      const m = await api.matchAudit(userId, "", 20);
      setMatches(m.items || []);
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    }
  }, [userId, toast]);

  useEffect(() => {
    load();
  }, [load]);

  if (!userId) {
    return (
      <div className="page">
        <p className="note">缺少 user_id</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <button type="button" className="btn ghost" onClick={() => navigate("/people")}>
            <ArrowLeft size={16} /> 人员
          </button>
          <h1 style={{ marginTop: 10 }}>{detail?.display_name || userId}</h1>
          <p>人员档案 · 人脸凭证与最近比对</p>
        </div>
        <button type="button" className="btn primary" onClick={() => navigate(`/people/${userId}/capture`)}>
          <Camera size={16} /> 采集
        </button>
      </div>

      <div className="card">
        <h3 className="card-title">身份</h3>
        <label className="field" htmlFor="rename">
          显示名
        </label>
        <div className="actions" style={{ marginBottom: 12 }}>
          <input
            id="rename"
            className="input"
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
          />
          <button
            type="button"
            className="btn"
            onClick={async () => {
              try {
                await api.renamePerson(userId, nameDraft);
                toast.push("已更新姓名");
                load();
              } catch {
                toast.push("保存失败");
              }
            }}
          >
            保存
          </button>
        </div>
        <p className="note mono">user_id {userId}</p>
        <div className="actions" style={{ marginTop: 12, alignItems: "center" }}>
          <span className="field" style={{ margin: 0 }}>
            刷脸可开门
          </span>
          <Switch.Root
            className="switch"
            checked={!!detail?.enabled && detail.face_status !== "rejected"}
            onCheckedChange={async (on) => {
              try {
                if (on) await api.enablePerson(userId);
                else await api.disablePerson(userId);
                toast.push(on ? "已启用" : "已停用");
                load();
              } catch {
                toast.push("操作失败");
              }
            }}
          >
            <Switch.Thumb className="switch-thumb" />
          </Switch.Root>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3 className="card-title" style={{ margin: 0 }}>
            人脸凭证
          </h3>
          {detail ? <StatusBadge status={detail.face_status} /> : null}
        </div>
        <p className="note">
          验证成功 {detail?.verify_ok_count ?? 0} · 连续失败 {detail?.verify_fail_streak ?? 0} · 合格帧{" "}
          {detail?.frame_count ?? 0}
        </p>
        <div className="thumbs" style={{ marginTop: 10 }}>
          {(detail?.frames || []).map((f) => (
            <div className="slot filled" key={f.index}>
              <img src={api.frameUrl(userId, f.index)} alt="" />
            </div>
          ))}
          {!detail?.frames?.length ? <p className="note">无本地帧 — 点上方「采集」开始</p> : null}
        </div>
        <div className="actions" style={{ marginTop: 14 }}>
          <Link className="btn primary" to={`/people/${userId}/capture`}>
            <Camera size={16} /> 开始采集
          </Link>
          <button type="button" className="btn danger" onClick={() => setPendingDelete(true)}>
            删除人员
          </button>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">最近比对</h3>
        {matches.length === 0 ? (
          <p className="note">暂无比对记录</p>
        ) : (
          <div className="table-card flat">
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>摄像头</th>
                  <th>相似度</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => (
                  <tr
                    key={m.id}
                    className="click-row"
                    onClick={() => navigate(`/audit?result=${m.decision === "request" ? "grant" : m.decision}`)}
                  >
                    <td className="muted">{fmtTime(m.created_at)}</td>
                    <td className="mono">{m.camera}</td>
                    <td className="mono">{m.similarity.toFixed(3)}</td>
                    <td className={`dec ${m.decision}`}>{m.decision}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete}
        title="删除人员记录？"
        description={`将删除 ${detail?.display_name || userId} 的本地向量与合格帧，不可恢复。`}
        confirmLabel="删除"
        onOpenChange={(o) => !o && setPendingDelete(false)}
        onConfirm={async () => {
          try {
            await api.deletePerson(userId);
            toast.push("已删除");
            navigate("/people");
          } catch {
            toast.push("删除失败");
          }
        }}
      />
    </div>
  );
}
