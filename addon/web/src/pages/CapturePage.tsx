import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Mic, Play, Square } from "lucide-react";
import { api, type Person } from "@/api/client";
import { PersonPicker } from "@/components/PersonPicker";
import { useToast } from "@/components/ui/Toast";

type Props = {
  /** 无路由 id 时的兼容入口（旧 /capture 重定向前） */
  allowPicker?: boolean;
};

export function CapturePage({ allowPicker = false }: Props) {
  const { userId: routeUserId } = useParams();
  const toast = useToast();
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const loopRef = useRef<number | null>(null);
  const sessionRef = useRef<string | null>(null);

  const [selected, setSelected] = useState<Person | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [needed, setNeeded] = useState(5);
  const [progress, setProgress] = useState(0);
  const [thumbs, setThumbs] = useState<(string | null)[]>([]);
  const [hint, setHint] = useState("准备摄像头…");
  const [hintOk, setHintOk] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [aiOk, setAiOk] = useState(false);
  const voiceRec = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    if (!routeUserId) {
      if (!allowPicker) {
        navigate("/people", { replace: true });
      }
      return;
    }
    let cancelled = false;
    api
      .personDetail(routeUserId)
      .then((d) => {
        if (!cancelled) {
          setSelected(d);
          setNameDraft(d.display_name || "");
          setHint(`将为 ${d.display_name || d.user_id} 采集 · 开始后自动质检送帧`);
        }
        api.aiStatus().then((s) => !cancelled && setAiOk(!!s.configured)).catch(() => undefined);
      })
      .catch(async () => {
        if (cancelled) return;
        // 云端有人、本地尚无档案：允许用 id 开会话
        try {
          const r = await api.searchPersons(routeUserId);
          const hit = (r.items || []).find((p) => p.user_id === routeUserId);
          setSelected(hit || { user_id: routeUserId, display_name: "", face_status: "none" });
          setHint("本地尚无档案 · 采集成功后写入底库");
        } catch {
          setSelected({ user_id: routeUserId, display_name: "", face_status: "none" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [routeUserId, allowPicker, navigate]);

  const ensureCamera = useCallback(async () => {
    if (streamRef.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    streamRef.current = stream;
    if (videoRef.current) videoRef.current.srcObject = stream;
  }, []);

  useEffect(() => {
    if (selected) {
      ensureCamera().catch((e) => toast.push(String(e.message || e)));
    }
  }, [selected, ensureCamera, toast]);

  useEffect(() => {
    return () => {
      if (loopRef.current) window.clearInterval(loopRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const stopLoop = useCallback((cancelServer: boolean) => {
    if (loopRef.current) {
      window.clearInterval(loopRef.current);
      loopRef.current = null;
    }
    if (cancelServer && sessionRef.current) {
      api.enrollCancel(sessionRef.current).catch(() => undefined);
      sessionRef.current = null;
      setSessionId(null);
    }
  }, []);

  const pushFrame = useCallback(async () => {
    const sid = sessionRef.current;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!sid || !video || !canvas) return;
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) return;
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d")?.drawImage(video, 0, 0, w, h);
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", 0.88));
    if (!blob) return;
    const j = await api.enrollFrame(sid, blob);
    if (typeof j.needed === "number") setNeeded(j.needed);
    if (typeof j.progress === "number") setProgress(j.progress);
    if (j.ok) {
      setHint(j.hint || "合格");
      setHintOk(true);
      const url = URL.createObjectURL(blob);
      setThumbs((prev) => {
        const next = [...prev];
        next[Math.max(0, (j.progress || 1) - 1)] = url;
        return next;
      });
    } else {
      setHint(j.hint || j.reason || "请调整");
      setHintOk(false);
    }
    setReason(j.reason || "");
    if (j.done) {
      stopLoop(false);
      sessionRef.current = null;
      setSessionId(null);
      setHint(`采集完成：${j.face_status || "accepted"} · 可让学生去门口试刷`);
      setHintOk(true);
      toast.push("✓ 已录入底库");
      setSelected((s) => (s ? { ...s, face_status: j.face_status || "accepted" } : s));
    }
  }, [stopLoop, toast]);

  const onStart = async () => {
    if (!selected || busy) return;
    setBusy(true);
    try {
      await ensureCamera();
      stopLoop(true);
      setProgress(0);
      setThumbs([]);
      setNeeded(5);
      const j = await api.enrollStart(selected.user_id, selected.display_name || "");
      sessionRef.current = j.session_id;
      setSessionId(j.session_id);
      setNeeded(j.needed || 5);
      setHint("会话进行中 · 自动质检送帧");
      setHintOk(true);
      loopRef.current = window.setInterval(() => {
        pushFrame().catch((e) => {
          setHint(String(e));
          setHintOk(false);
        });
      }, 650);
    } catch (e) {
      setHint(String(e instanceof Error ? e.message : e));
      setHintOk(false);
    } finally {
      setBusy(false);
    }
  };

  const onStop = () => {
    stopLoop(true);
    setHint("会话已结束");
    setHintOk(null);
  };

  const backTo = routeUserId ? `/people/${routeUserId}` : "/people";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <button type="button" className="btn ghost" onClick={() => navigate(backTo)}>
            <ArrowLeft size={16} /> 返回
          </button>
          <h1 style={{ marginTop: 10 }}>采集</h1>
          <p>
            {selected
              ? `${selected.display_name || selected.user_id} · 仅摄像头实时采集`
              : "仅摄像头实时采集 · 开始后自动质检送帧"}
          </p>
        </div>
      </div>

      {allowPicker && !routeUserId ? <PersonPicker selected={selected} onSelect={setSelected} /> : null}

      {selected && (
        <div className="panel" style={{ marginTop: 12 }}>
          <h3>显示名</h3>
          <div className="row-gap">
            <input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              placeholder="显示名"
            />
            {aiOk && (
              <button
                type="button"
                className="btn ghost"
                onMouseDown={async () => {
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
                          setNameDraft(r.text);
                          await api.renamePerson(selected.user_id, r.text);
                        }
                      } catch (e) {
                        toast.push(String(e instanceof Error ? e.message : e));
                      }
                    };
                    voiceRec.current = rec;
                    rec.start();
                  } catch (e) {
                    toast.push(String(e instanceof Error ? e.message : e));
                  }
                }}
                onMouseUp={() => {
                  voiceRec.current?.stop();
                  voiceRec.current = null;
                }}
                onTouchStart={(e) => {
                  e.preventDefault();
                  (e.currentTarget as HTMLButtonElement).dispatchEvent(new MouseEvent("mousedown"));
                }}
                onTouchEnd={(e) => {
                  e.preventDefault();
                  (e.currentTarget as HTMLButtonElement).dispatchEvent(new MouseEvent("mouseup"));
                }}
              >
                <Mic size={16} /> 按住说话
              </button>
            )}
            <button
              type="button"
              className="btn ghost"
              onClick={async () => {
                try {
                  await api.renamePerson(selected.user_id, nameDraft.trim());
                  toast.push("已更新显示名");
                } catch (e) {
                  toast.push(String(e instanceof Error ? e.message : e));
                }
              }}
            >
              保存
            </button>
          </div>
        </div>
      )}

      <div className="capture-grid" style={{ marginTop: 14 }}>
        <div className="stage">
          <video ref={videoRef} playsInline autoPlay muted />
          <div className="guide" aria-hidden />
        </div>
        <div className="side-stack">
          <div className="card">
            <div className="progress-row">
              <span>
                进度 <b>{progress} / {needed}</b>
              </span>
              <div className="dots">
                {Array.from({ length: needed }).map((_, i) => (
                  <span key={i} className={i < progress ? "on" : ""} />
                ))}
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <div className={`hint${hintOk === true ? " ok" : hintOk === false ? " bad" : ""}`}>
                {hint}
              </div>
              {reason ? (
                <p className="note" style={{ marginTop: 8 }}>
                  原因码 <code style={{ fontFamily: "var(--mono)" }}>{reason}</code>
                </p>
              ) : null}
            </div>
            <div className="actions" style={{ marginTop: 14 }}>
              <button
                type="button"
                className="btn primary"
                disabled={!selected || !!sessionId || busy}
                onClick={onStart}
              >
                <Play size={16} /> 开始会话
              </button>
              <button type="button" className="btn danger" disabled={!sessionId} onClick={onStop}>
                <Square size={16} /> 结束
              </button>
            </div>
            <p className="note" style={{ marginTop: 12 }}>
              不提供相册上传。让学生站好即可。
              {routeUserId ? (
                <>
                  {" "}
                  <Link className="linkish" to={`/people/${routeUserId}`}>
                    回档案
                  </Link>
                </>
              ) : null}
            </p>
          </div>
          <div className="card">
            <div className="field">合格帧</div>
            <div className="thumbs">
              {Array.from({ length: needed }).map((_, i) => (
                <div key={i} className={`slot${thumbs[i] ? " filled" : ""}`}>
                  {thumbs[i] ? <img src={thumbs[i]!} alt="" /> : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
}
