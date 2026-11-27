import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MapPinned, Shield, Users } from "lucide-react";
import { api, type Space } from "@/api/client";
import { useToast } from "@/components/ui/Toast";

export function SpacesPage() {
  const toast = useToast();
  const [items, setItems] = useState<Space[]>([]);

  const load = useCallback(async () => {
    try {
      const r = await api.listSpaces();
      setItems(r.items || []);
    } catch (e) {
      toast.push(String(e instanceof Error ? e.message : e));
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>空间</h1>
          <p>门、房间、通道 — 画面与布防挂在这里</p>
        </div>
      </div>
      <div className="card-list">
        {items.map((s) => (
          <Link key={s.id} to={`/spaces/${encodeURIComponent(s.id)}`} className="space-card">
            <div className="space-card-ico">
              <MapPinned size={20} />
            </div>
            <div className="space-card-body">
              <div className="space-card-title">{s.name || s.id}</div>
              <div className="muted">
                {s.kind} · 人≈{Number(s.person_count || 0).toFixed(1)}
                {s.armed ? " · 布防" : ""}
              </div>
            </div>
            <div className="space-card-meta">
              {s.armed ? <Shield size={16} /> : null}
              {(s.person_count || 0) > 0.1 ? <Users size={16} /> : null}
            </div>
          </Link>
        ))}
        {items.length === 0 && <p className="muted">还没有空间。启动时会从门口配置种子一个。</p>}
      </div>
    </div>
  );
}
