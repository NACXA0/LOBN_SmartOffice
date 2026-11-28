import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload } from "lucide-react";
import { api } from "@/api/client";
import { Drawer } from "@/components/ui/Drawer";
import { useToast } from "@/components/ui/Toast";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated?: () => void;
};

export function CreatePersonDrawer({ open, onOpenChange, onCreated }: Props) {
  const toast = useToast();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [userId, setUserId] = useState("");
  const [kind, setKind] = useState("staff");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);

  function reset() {
    setName("");
    setUserId("");
    setKind("staff");
    setPhone("");
    setNotes("");
    setFiles([]);
  }

  async function submit() {
    const display = name.trim();
    if (!display) {
      toast.push("请填写姓名");
      return;
    }
    setBusy(true);
    try {
      const p = await api.createPerson({
        display_name: display,
        user_id: userId.trim() || undefined,
        person_kind: kind,
        phone: phone.trim(),
        notes: notes.trim(),
      });
      if (files.length) {
        const up = await api.uploadPersonPhotos(p.user_id, files);
        toast.push(
          up.rejected?.length
            ? `已建档 · 入库 ${up.added} 张，${up.rejected.length} 张未通过`
            : `已建档并入库 ${up.added} 张人脸`,
        );
      } else {
        toast.push("已建档 · 可稍后上传照片或现场采集");
      }
      reset();
      onOpenChange(false);
      onCreated?.();
      navigate(`/people/${p.user_id}`);
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
      title="新建人员"
      footer={
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => onOpenChange(false)}>
            取消
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={submit}>
            {busy ? "保存中…" : "保存"}
          </button>
        </>
      }
    >
      <p className="note" style={{ marginBottom: 12 }}>
        未进过办公室也可先建档：填信息 + 上传人脸照片（或稍后现场采集）。预约平台录入只是凭证，与造访分开。
      </p>
      <label className="field" htmlFor="cp-name">
        姓名 *
      </label>
      <input
        id="cp-name"
        className="input"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="显示名"
      />
      <label className="field" htmlFor="cp-kind">
        身份
      </label>
      <select id="cp-kind" className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
        <option value="staff">员工</option>
        <option value="student">学员</option>
        <option value="visitor">访客</option>
      </select>
      <label className="field" htmlFor="cp-uid">
        user_id（可选）
      </label>
      <input
        id="cp-uid"
        className="input"
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        placeholder="空则自动生成；可填预约平台 ID 便于关联"
      />
      <label className="field" htmlFor="cp-phone">
        电话（可选）
      </label>
      <input id="cp-phone" className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <label className="field" htmlFor="cp-notes">
        备注
      </label>
      <textarea
        id="cp-notes"
        className="input"
        rows={3}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="用途说明、授权范围等"
      />
      <label className="field">人脸照片（可选，可多选）</label>
      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 12))}
      />
      <button type="button" className="btn" onClick={() => fileRef.current?.click()}>
        <Upload size={16} /> {files.length ? `已选 ${files.length} 张` : "从相册选择"}
      </button>
      {files.length > 0 ? (
        <ul className="mini-list" style={{ marginTop: 8 }}>
          {files.map((f) => (
            <li key={f.name + f.size}>
              <span className="note">{f.name}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </Drawer>
  );
}
