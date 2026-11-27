import { useRef, useState } from "react";
import { MessageCircle, X, Send, Mic, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useToast } from "@/components/ui/Toast";

const CHIPS = [
  { label: "谁在场？", q: "现在哪些空间有人？" },
  { label: "待处理告警", q: "有哪些待处理告警？" },
  { label: "今日放行", q: "今天放过谁？来源是什么？" },
  { label: "布防状态", q: "哪些空间在布防？" },
  { label: "下一窗口", q: "接下来的策略窗口是谁？" },
];

export function AssistantDrawer() {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [actions, setActions] = useState<{ label: string; path: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [aiOk, setAiOk] = useState(false);
  const [mode, setMode] = useState("");
  const recRef = useRef<MediaRecorder | null>(null);

  async function ensureAi() {
    try {
      const s = await api.aiStatus();
      setAiOk(!!s.configured);
    } catch {
      setAiOk(false);
    }
  }

  async function ask(question?: string) {
    const text = (question ?? q).trim();
    if (!text || busy) return;
    setBusy(true);
    setQ(text);
    try {
      const r = await api.assist(text);
      setAnswer(r.text || "");
      setActions(r.actions || []);
      setMode(r.mode || "");
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
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
            if (r.text) {
              setQ(r.text);
              await ask(r.text);
            }
          } catch (e) {
            toast.push(String(e instanceof Error ? e.message : e));
          }
        };
        recRef.current = rec;
        rec.start();
      } catch (e) {
        toast.push(String(e instanceof Error ? e.message : e));
      }
    } else if (recRef.current) {
      recRef.current.stop();
      recRef.current = null;
    }
  }

  return (
    <>
      <button
        type="button"
        className="assist-fab"
        onClick={() => {
          setOpen(true);
          ensureAi();
        }}
        aria-label="助理"
      >
        <MessageCircle size={20} />
      </button>
      {open && (
        <div className="drawer-backdrop" onClick={() => setOpen(false)}>
          <div className="drawer-panel assist-panel" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <strong>
                <Sparkles size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
                办公室助理
              </strong>
              <button type="button" className="icon-btn" onClick={() => setOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="chip-list" style={{ marginBottom: 12 }}>
              {CHIPS.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  className="info-chip clickable"
                  disabled={busy}
                  onClick={() => ask(c.q)}
                >
                  {c.label}
                </button>
              ))}
            </div>

            <div className="assist-input-row">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="或直接提问…"
                onKeyDown={(e) => e.key === "Enter" && ask()}
              />
              {aiOk && (
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
              )}
              <button type="button" className="btn" disabled={busy} onClick={() => ask()}>
                <Send size={16} />
              </button>
            </div>

            {answer && (
              <>
                {mode && <div className="muted" style={{ marginBottom: 6 }}>{mode === "online" ? "在线整理" : "本地条目"}</div>}
                <pre className="assist-answer">{answer}</pre>
              </>
            )}
            {actions.length > 0 && (
              <div className="assist-actions">
                {actions.map((a, i) => (
                  <Link
                    key={`${a.path}-${i}`}
                    to={a.path}
                    className="btn ghost"
                    onClick={() => setOpen(false)}
                  >
                    {a.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
