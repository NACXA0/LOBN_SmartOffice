export type FaceStatus = "none" | "pending" | "accepted" | "verified" | "rejected" | string;

export type Person = {
  user_id: string;
  display_name: string;
  face_status: FaceStatus;
  enabled?: boolean;
  has_thumb?: boolean;
  source?: string;
  verify_ok_count?: number;
  verify_fail_streak?: number;
  updated_at?: number;
  frame_count?: number;
  ha_person_entity?: string;
  person_kind?: string;
  origin?: string;
  linked_user_id?: string;
  first_seen_at?: number | null;
  last_seen_at?: number | null;
  visit_count?: number;
  sighted?: boolean;
  can_open?: boolean;
  valid_until?: number | null;
  allowed_spaces?: string;
  notes?: string;
  phone?: string;
  ignored?: boolean;
};

export type PersonPhoto = {
  id: number;
  url: string;
  created_at?: number;
  has_file?: boolean;
};

export type VisitRow = {
  id: number;
  user_id: string;
  space_id: string;
  camera: string;
  kind: string;
  similarity: number;
  detail: Record<string, unknown>;
  created_at: number;
};

export type AuditRow = {
  id: number;
  source: string;
  door: string;
  user_id: string | null;
  display_name?: string;
  result: string;
  reason: string;
  command_id?: string | null;
  detail: Record<string, unknown>;
  created_at: number;
};

/** 人脸比对明细 */
export type MatchAuditRow = {
  id: number;
  user_id: string | null;
  camera: string;
  similarity: number;
  decision: string;
  detail: Record<string, unknown>;
  created_at: number;
};

export type Health = {
  ok: boolean;
  embedder_ready: boolean;
  model_version?: string;
  disk_full?: boolean;
  mqtt_enabled?: boolean;
  mqtt_host?: string;
  store?: Record<string, number>;
  open_sessions?: number;
};

export type Dashboard = {
  persons: {
    total: number;
    enabled_door: number;
    sighted?: number;
    strangers?: number;
    credential_only?: number;
    visits_h24?: number;
    by_status: Record<string, number>;
    pending_recollect: { user_id: string; display_name: string; face_status: string; updated_at: number }[];
  };
  access: {
    h24: { grant: number; drop?: number; deny: number; skip: number; by_source?: Record<string, number> };
    d7: { grant: number; drop?: number; deny: number; skip: number; by_source?: Record<string, number> };
    top_grant_7d: { user_id: string; n: number }[];
  };
  office?: {
    open_alerts: number;
    occupied_spaces: number;
    armed_spaces: number;
    visitors_expiring?: { user_id: string; display_name: string; valid_until: number }[];
  };
  overlapping_spaces?: string[];
  store: Record<string, number>;
  runtime: {
    embedder_ready: boolean;
    model_version?: string;
    mqtt_enabled?: boolean;
    mqtt_host?: string;
    disk_full?: boolean;
    open_sessions?: number;
    ai_configured?: boolean;
    db_ok?: boolean;
  };
};

export type SpaceRegion = { id: string; name: string; points: number[][] };

export type Space = {
  id: string;
  name: string;
  kind: string;
  camera?: string;
  door_node?: string;
  polygon?: number[][];
  zones?: SpaceRegion[];
  motion_masks?: SpaceRegion[];
  object_masks?: SpaceRegion[];
  motion_cfg?: Record<string, unknown>;
  track_cfg?: { labels?: string[]; filters?: Record<string, { min_score?: number; min_area?: number }> };
  audio_cfg?: { enabled?: boolean; min_rms?: number; cooldown_sec?: number };
  armed?: boolean;
  arm_override?: boolean | null;
  person_count?: number;
  access_mode?: "face" | "schedule" | "always_open" | "armed_only" | string;
  scene_ids?: string[];
  updated_at?: number;
  windows?: { id: string; subject_id: string; window_start: number; window_end: number }[];
  arming_plan?: unknown[];
  alerts?: { id: number; kind: string; title: string }[];
};

export type AlertRow = {
  id: number;
  space_id: string;
  kind: string;
  severity: string;
  title: string;
  detail: Record<string, unknown>;
  created_at: number;
  acked: boolean;
};

export type PersonDetail = Person & {
  frame_count: number;
  frames: { index: number; url: string; id?: number }[];
  photos?: PersonPhoto[];
  visits?: VisitRow[];
};

declare global {
  interface Window {
    SMARTCENTER_API?: string;
    SMARTOFFICE_API?: string;
  }
}

function apiBase(): string {
  const q = new URLSearchParams(location.search).get("api");
  const raw = (q || window.SMARTOFFICE_API || window.SMARTCENTER_API || "").replace(/\/$/, "");
  return raw;
}

export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(apiUrl(path), init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") throw new Error(detail);
    if (detail && typeof detail === "object" && "reason" in (detail as object)) {
      throw new Error(String((detail as { reason: string }).reason));
    }
    throw new Error(r.statusText || "request_failed");
  }
  return body as T;
}

export const api = {
  health: () => json<Health>("/healthz"),
  stats: () => json<Dashboard>("/api/stats"),
  searchPersons: (q: string) => json<{ items: Person[] }>(`/api/persons/search?q=${encodeURIComponent(q)}`),
  listPersons: (q = "", scope = "all") => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (scope && scope !== "all") qs.set("scope", scope);
    const s = qs.toString();
    return json<{ items: Person[]; scope?: string }>(`/api/persons${s ? `?${s}` : ""}`);
  },
  personDetail: (uid: string) => json<PersonDetail>(`/api/persons/${encodeURIComponent(uid)}`),
  createPerson: (body: {
    display_name: string;
    user_id?: string;
    person_kind?: string;
    notes?: string;
    phone?: string;
    enabled?: boolean;
    valid_until?: number | null;
    allowed_spaces?: string;
  }) =>
    json<Person>("/api/persons", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchPerson: (
    uid: string,
    body: {
      display_name?: string;
      person_kind?: string;
      notes?: string;
      phone?: string;
      ignored?: boolean;
      enabled?: boolean;
      valid_until?: number | null;
      set_valid_until?: boolean;
      allowed_spaces?: string;
    },
  ) =>
    json<Person>(`/api/persons/${encodeURIComponent(uid)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  personVisits: (uid: string, limit = 40) =>
    json<{ items: VisitRow[] }>(`/api/persons/${encodeURIComponent(uid)}/visits?limit=${limit}`),
  linkPerson: (uid: string, target_user_id: string) =>
    json<Person>(`/api/persons/${encodeURIComponent(uid)}/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_user_id }),
    }),
  renamePerson: (uid: string, display_name: string) =>
    json<Person>(`/api/persons/${encodeURIComponent(uid)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name }),
    }),
  uploadPersonPhotos: async (uid: string, files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return json<{
      ok: boolean;
      added: number;
      total: number;
      pruned?: number;
      rejected?: { name?: string; reason?: string }[];
      person?: Person;
    }>(`/api/persons/${encodeURIComponent(uid)}/photos`, { method: "POST", body: fd });
  },
  deletePersonPhoto: (uid: string, embId: number) =>
    json<{ ok: boolean }>(`/api/persons/${encodeURIComponent(uid)}/photos/${embId}`, {
      method: "DELETE",
    }),
  enablePerson: (uid: string) => json(`/api/persons/${encodeURIComponent(uid)}/enable`, { method: "POST" }),
  disablePerson: (uid: string) => json(`/api/persons/${encodeURIComponent(uid)}/disable`, { method: "POST" }),
  deletePerson: (uid: string) => json(`/api/persons/${encodeURIComponent(uid)}`, { method: "DELETE" }),
  thumbUrl: (uid: string) => apiUrl(`/api/persons/${encodeURIComponent(uid)}/thumb`),
  frameUrl: (uid: string, index: number) => apiUrl(`/api/persons/${encodeURIComponent(uid)}/frame/${index}`),
  photoUrl: (uid: string, embId: number) =>
    apiUrl(`/api/persons/${encodeURIComponent(uid)}/photos/${embId}`),
  audit: (result = "", limit = 80, source = "") => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (result) qs.set("result", result);
    if (source) qs.set("source", source);
    return json<{ items: AuditRow[] }>(`/api/audit?${qs}`);
  },
  matchAudit: (userId = "", decision = "", limit = 40) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (userId) qs.set("user_id", userId);
    if (decision) qs.set("decision", decision);
    return json<{ items: MatchAuditRow[] }>(`/api/match-audit?${qs}`);
  },
  enrollStart: (user_id: string, display_name: string) =>
    json<{ session_id: string; needed: number }>("/api/enroll/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id, display_name, channel: "staff" }),
    }),
  enrollFrame: async (sessionId: string, blob: Blob) => {
    const fd = new FormData();
    fd.append("file", blob, "frame.jpg");
    return json<{
      ok: boolean;
      reason?: string;
      hint?: string;
      progress?: number;
      needed?: number;
      done?: boolean;
      face_status?: string;
    }>(`/api/enroll/${sessionId}/frame`, { method: "POST", body: fd });
  },
  enrollCancel: (sessionId: string) =>
    json(`/api/enroll/${sessionId}/cancel`, { method: "POST" }),
  listSpaces: () => json<{ items: Space[] }>("/api/spaces"),
  spaceDetail: (id: string) => json<Space>(`/api/spaces/${encodeURIComponent(id)}`),
  setPolygon: (id: string, polygon: number[][]) =>
    json<Space>(`/api/spaces/${encodeURIComponent(id)}/polygon`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ polygon }),
    }),
  setRegions: (
    id: string,
    body: { zones?: SpaceRegion[]; motion_masks?: SpaceRegion[]; object_masks?: SpaceRegion[] },
  ) =>
    json<Space>(`/api/spaces/${encodeURIComponent(id)}/regions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchVision: (
    id: string,
    body: {
      motion_cfg?: Record<string, unknown>;
      track_cfg?: Record<string, unknown>;
      audio_cfg?: Record<string, unknown>;
    },
  ) =>
    json<Space>(`/api/spaces/${encodeURIComponent(id)}/vision`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  visionLabels: () =>
    json<{
      items: string[];
      defaults: string[];
      zh?: Record<string, string>;
      catalog?: { id: string; zh: string }[];
    }>("/api/vision/labels"),
  manualOpen: (id: string, note = "") =>
    json<{ ok: boolean; reason: string; command_id?: string }>(
      `/api/spaces/${encodeURIComponent(id)}/open`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note }),
      },
    ),
  setArm: (id: string, body: { armed?: boolean; override?: boolean; schedule?: unknown[] }) =>
    json<Space>(`/api/spaces/${encodeURIComponent(id)}/arm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  setAccessMode: (id: string, access_mode: string) =>
    json<Space>(`/api/spaces/${encodeURIComponent(id)}/access-mode`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_mode }),
    }),
  listScenes: () =>
    json<{ items: { id: string; name: string; kind: string; adapter: string; space_ids: string[]; enabled: boolean }[] }>(
      "/api/scenes",
    ),
  sceneDetail: (id: string) =>
    json<Record<string, unknown>>(`/api/scenes/${encodeURIComponent(id)}`),
  upsertScene: (body: {
    id: string;
    name?: string;
    kind?: string;
    adapter?: string;
    space_ids?: string[];
    enabled?: boolean;
  }) =>
    json(`/api/scenes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  listAlerts: (acked: boolean | null = false) => {
    const qs = new URLSearchParams();
    if (acked !== null) qs.set("acked", String(acked));
    return json<{ items: AlertRow[] }>(`/api/alerts?${qs}`);
  },
  ackAlert: (id: number) => json(`/api/alerts/${id}/ack`, { method: "POST" }),
  strangers: (limit = 40) => json<{ items: (MatchAuditRow & { bucket: string })[] }>(`/api/match-strangers?limit=${limit}`),
  aiStatus: () => json<{ configured: boolean; model?: string }>("/api/ai/status"),
  explainCrop: (record_id: number, kind: "match" | "alert" = "match") =>
    json<{ ok: boolean; text?: string; reason?: string }>("/api/ai/explain-crop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record_id, kind }),
    }),
  explainSpace: (space_id: string, prompt = "") =>
    json<{ ok: boolean; text?: string; reason?: string }>("/api/ai/explain-space", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ space_id, prompt }),
    }),
  vlmAlert: (alert_id: number) =>
    json<{ ok: boolean; text?: string }>("/api/ai/vlm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alert_id }),
    }),
  transcribe: async (blob: Blob) => {
    const fd = new FormData();
    fd.append("file", blob, "note.webm");
    return json<{ ok: boolean; text?: string }>("/api/ai/transcribe", { method: "POST", body: fd });
  },
  assist: (question: string, session_id = "default") =>
    json<{ ok: boolean; text: string; mode?: string; actions?: { label: string; path: string }[] }>(
      "/api/ai/assist",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id }),
      },
    ),
};
