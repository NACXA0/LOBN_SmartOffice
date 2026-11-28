import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as Switch from "@radix-ui/react-switch";
import { ArrowLeft, Camera, Link2, Trash2, Upload } from "lucide-react";
import { api, type MatchAuditRow, type PersonDetail, type VisitRow } from "@/api/client";
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
  const fileRef = useRef<HTMLInputElement>(null);
  const [detail, setDetail] = useState<PersonDetail | null>(null);
  const [nameDraft, setNameDraft] = useState("");
  const [kind, setKind] = useState("staff");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [matches, setMatches] = useState<MatchAuditRow[]>([]);
  const [visits, setVisits] = useState<VisitRow[]>([]);
  const [linkTarget, setLinkTarget] = useState("");
  const [pendingDelete, setPendingDelete] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const d = await api.personDetail(userId);
      setDetail(d);
      setNameDraft(d.display_name || "");
      setKind(d.person_kind || "staff");
      setPhone(d.phone || "");
      setNotes(d.notes || "");
      setVisits(d.visits || []);
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

  const isStranger = detail?.person_kind === "stranger";
  const photos = detail?.photos?.length
    ? detail.photos
    : (detail?.frames || []).map((f) => ({
        id: f.id || f.index,
        url: f.url.startsWith("http") || f.url.startsWith("/") ? api.frameUrl(userId, f.index) : f.url,
      }));

  async function saveProfile() {
    try {
      await api.patchPerson(userId, {
        display_name: nameDraft.trim(),
        person_kind: kind,
        phone: phone.trim(),
        notes: notes.trim(),
      });
      toast.push("档案已保存");
      load();
    } catch {
      toast.push("保存失败");
    }
  }

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      const r = await api.uploadPersonPhotos(userId, Array.from(files).slice(0, 12));
      toast.push(
        r.rejected?.length
          ? `入库 ${r.added} 张，跳过 ${r.rejected.length} 张`
          : `已追加 ${r.added} 张参考人脸`,
      );
      load();
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <button type="button" className="btn ghost" onClick={() => navigate("/people")}>
            <ArrowLeft size={16} /> 人员
          </button>
          <h1 style={{ marginTop: 10 }}>{detail?.display_name || userId}</h1>
          <p>
            {isStranger
              ? "监控自动建档 · 可关联正式身份或标记忽略"
              : "档案 / 相册入库 / 现场采集 · 凭证与造访分开"}
          </p>
        </div>
        <div className="row-gap">
          <button type="button" className="btn" disabled={uploading} onClick={() => fileRef.current?.click()}>
            <Upload size={16} /> {uploading ? "上传中…" : "上传照片"}
          </button>
          <button type="button" className="btn primary" onClick={() => navigate(`/people/${userId}/capture`)}>
            <Camera size={16} /> 现场采集
          </button>
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(e) => onUpload(e.target.files)}
      />

      <div className="card">
        <h3 className="card-title">身份档案</h3>
        <div className="chip-list" style={{ marginBottom: 12 }}>
          <span className="pill">{detail?.origin === "booking" ? "来源·预约" : detail?.origin === "manual" ? "来源·手工" : "来源·办公室"}</span>
          {detail?.sighted ? <span className="pill">已造访</span> : <span className="pill">未造访</span>}
          <span className="pill">造访 {detail?.visit_count ?? 0}</span>
          {detail?.ignored ? <span className="pill warn">已忽略</span> : null}
        </div>
        <label className="field" htmlFor="rename">
          显示名
        </label>
        <input id="rename" className="input" value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} />
        <label className="field" htmlFor="kind">
          身份类型
        </label>
        <select id="kind" className="input" value={kind} onChange={(e) => setKind(e.target.value)} disabled={isStranger}>
          <option value="staff">员工</option>
          <option value="student">学员</option>
          <option value="visitor">访客</option>
          {isStranger ? <option value="stranger">陌生人</option> : null}
        </select>
        <label className="field" htmlFor="phone">
          电话
        </label>
        <input id="phone" className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <label className="field" htmlFor="notes">
          备注
        </label>
        <textarea id="notes" className="input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <p className="note mono" style={{ marginTop: 8 }}>
          user_id {userId}
        </p>
        <div className="actions" style={{ marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button type="button" className="btn primary" onClick={saveProfile}>
            保存档案
          </button>
          {!isStranger ? (
            <>
              <span className="field" style={{ margin: 0 }}>
                刷脸可开门
              </span>
              <Switch.Root
                className="switch"
                checked={!!detail?.can_open}
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
            </>
          ) : null}
          <span className="field" style={{ margin: 0 }}>
            忽略此人
          </span>
          <Switch.Root
            className="switch"
            checked={!!detail?.ignored}
            onCheckedChange={async (on) => {
              try {
                await api.patchPerson(userId, { ignored: on });
                toast.push(on ? "已忽略（再识别不告警）" : "已取消忽略");
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

      {isStranger ? (
        <div className="card">
          <h3 className="card-title">
            <Link2 size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
            关联正式身份
          </h3>
          <p className="note">与预约平台或已有人员是同一人时，填入其 user_id 合并档案与造访。</p>
          <div className="actions" style={{ marginTop: 10 }}>
            <input
              className="input"
              placeholder="目标 user_id"
              value={linkTarget}
              onChange={(e) => setLinkTarget(e.target.value)}
            />
            <button
              type="button"
              className="btn primary"
              onClick={async () => {
                const t = linkTarget.trim();
                if (!t) return;
                try {
                  await api.linkPerson(userId, t);
                  toast.push("已关联合并");
                  navigate(`/people/${t}`, { replace: true });
                } catch {
                  toast.push("关联失败 — 确认目标已存在");
                }
              }}
            >
              合并
            </button>
          </div>
        </div>
      ) : null}

      <div className="card">
        <div className="card-head">
          <h3 className="card-title" style={{ margin: 0 }}>
            人脸参考图
          </h3>
          {detail ? <StatusBadge status={detail.face_status} /> : null}
        </div>
        <p className="note">
          每张图都是可见参考点（对齐 FaceID 相册入库）。上限约 20 张；可删单张。验证{" "}
          {detail?.verify_ok_count ?? 0} · 失败连击 {detail?.verify_fail_streak ?? 0}
        </p>
        <div className="thumbs" style={{ marginTop: 10 }}>
          {photos.map((ph) => (
            <div className="slot filled" key={ph.id} style={{ position: "relative" }}>
              <img
                src={api.photoUrl(userId, ph.id)}
                alt=""
                onError={(e) => {
                  (e.target as HTMLImageElement).style.opacity = "0.3";
                }}
              />
              <button
                type="button"
                className="icon-btn"
                title="删除此参考图"
                style={{ position: "absolute", top: 4, right: 4 }}
                onClick={async () => {
                  try {
                    await api.deletePersonPhoto(userId, ph.id);
                    toast.push("已删除参考图");
                    load();
                  } catch {
                    toast.push("删除失败");
                  }
                }}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {!photos.length ? <p className="note">尚无参考图 — 上传照片或现场采集</p> : null}
        </div>
        <div className="actions" style={{ marginTop: 14 }}>
          <button type="button" className="btn" disabled={uploading} onClick={() => fileRef.current?.click()}>
            <Upload size={16} /> 上传照片
          </button>
          <Link className="btn primary" to={`/people/${userId}/capture`}>
            <Camera size={16} /> 现场采集
          </Link>
          <button type="button" className="btn danger" onClick={() => setPendingDelete(true)}>
            删除人员
          </button>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">造访记录</h3>
        <p className="note">监控识别到才记；手工建档或预约录入本身不算造访。</p>
        {visits.length === 0 ? (
          <p className="note">尚无造访</p>
        ) : (
          <div className="table-card flat">
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>摄像头</th>
                  <th>类型</th>
                  <th>相似度</th>
                </tr>
              </thead>
              <tbody>
                {visits.map((v) => (
                  <tr key={v.id}>
                    <td className="muted">{fmtTime(v.created_at)}</td>
                    <td className="mono">{v.camera || "—"}</td>
                    <td>{v.kind}</td>
                    <td className="mono">{Number(v.similarity || 0).toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
        description={`将删除 ${detail?.display_name || userId} 的向量、造访与参考图，不可恢复。`}
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
