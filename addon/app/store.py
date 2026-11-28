from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
  user_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL DEFAULT '',
  face_status TEXT NOT NULL DEFAULT 'none',
  enabled INTEGER NOT NULL DEFAULT 1,
  verify_ok_count INTEGER NOT NULL DEFAULT 0,
  verify_fail_streak INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  ha_person_entity TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS embeddings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector BLOB NOT NULL,
  frame_path TEXT,
  created_at REAL NOT NULL,
  FOREIGN KEY(user_id) REFERENCES persons(user_id)
);
CREATE INDEX IF NOT EXISTS idx_emb_user ON embeddings(user_id);
CREATE TABLE IF NOT EXISTS cooldowns (
  user_id TEXT PRIMARY KEY,
  until_mono REAL NOT NULL,
  until_wall REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS door_cooldowns (
  door TEXT PRIMARY KEY,
  until_mono REAL NOT NULL,
  until_wall REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS grants_seen (
  command_id TEXT PRIMARY KEY,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS match_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  camera TEXT,
  similarity REAL,
  decision TEXT,
  detail TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS access_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  door TEXT NOT NULL,
  user_id TEXT,
  display_name TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  command_id TEXT,
  detail TEXT,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON match_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON match_audit(decision);
CREATE INDEX IF NOT EXISTS idx_grants_created ON grants_seen(created_at);
CREATE INDEX IF NOT EXISTS idx_access_created ON access_ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_access_result ON access_ledger(result);
CREATE TABLE IF NOT EXISTS spaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'room',
  camera TEXT NOT NULL DEFAULT '',
  door_node TEXT NOT NULL DEFAULT '',
  polygon TEXT NOT NULL DEFAULT '[]',
  zones TEXT NOT NULL DEFAULT '[]',
  motion_masks TEXT NOT NULL DEFAULT '[]',
  object_masks TEXT NOT NULL DEFAULT '[]',
  motion_cfg TEXT NOT NULL DEFAULT '{}',
  track_cfg TEXT NOT NULL DEFAULT '{}',
  audio_cfg TEXT NOT NULL DEFAULT '{}',
  armed INTEGER NOT NULL DEFAULT 0,
  arm_override INTEGER,
  person_count REAL NOT NULL DEFAULT 0,
  access_mode TEXT NOT NULL DEFAULT 'face',
  scene_ids TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS scenes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'classroom',
  adapter TEXT NOT NULL DEFAULT '',
  space_ids TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  space_id TEXT,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'warn',
  title TEXT NOT NULL DEFAULT '',
  detail TEXT,
  frame_path TEXT,
  latch_key TEXT,
  created_at REAL NOT NULL,
  acked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_kind ON alerts(kind);
CREATE INDEX IF NOT EXISTS idx_alerts_acked ON alerts(acked);
CREATE TABLE IF NOT EXISTS assets (
  tag_id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  space_id TEXT NOT NULL DEFAULT '',
  custodian TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_windows (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  subject_id TEXT NOT NULL DEFAULT '',
  subject_name TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  window_start REAL NOT NULL,
  window_end REAL NOT NULL,
  rev TEXT NOT NULL DEFAULT '',
  raw TEXT,
  pulled_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_end ON policy_windows(window_end);
CREATE INDEX IF NOT EXISTS idx_policy_space ON policy_windows(space_id);
CREATE TABLE IF NOT EXISTS arming_plans (
  space_id TEXT PRIMARY KEY,
  schedule TEXT NOT NULL DEFAULT '[]',
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rfid_seen (
  event_id TEXT PRIMARY KEY,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rfid_seen_created ON rfid_seen(created_at);
CREATE TABLE IF NOT EXISTS allowlist_meta (
  room TEXT PRIMARY KEY,
  rev INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  space_id TEXT NOT NULL DEFAULT '',
  camera TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'sight',
  similarity REAL NOT NULL DEFAULT 0,
  detail TEXT,
  created_at REAL NOT NULL,
  FOREIGN KEY(user_id) REFERENCES persons(user_id)
);
CREATE INDEX IF NOT EXISTS idx_visits_user ON visits(user_id);
CREATE INDEX IF NOT EXISTS idx_visits_created ON visits(created_at);
"""


@dataclass
class PersonRow:
    user_id: str
    display_name: str
    face_status: str
    enabled: bool
    verify_ok_count: int
    verify_fail_streak: int
    updated_at: float = 0.0
    ha_person_entity: str = ""
    person_kind: str = "staff"  # staff|student|visitor|stranger
    valid_until: float | None = None
    allowed_spaces: str = ""  # comma-separated space ids; empty = all
    # office vs booking：凭证可来自预约平台；sighted/visits 才表示真实造访
    origin: str = "office"  # office|booking|manual
    linked_user_id: str = ""  # 陌生人关联到的正式身份
    first_seen_at: float | None = None
    last_seen_at: float | None = None
    visit_count: int = 0
    sighted: bool = False  # 是否曾在办公室被监控识别到
    notes: str = ""
    phone: str = ""
    ignored: bool = False  # 忽略：再识别但不告警/不推荐关联（对齐 FaceID ignore）


class GalleryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        # 长时间写入友好：WAL + 适度同步
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()
        self._mem: dict[str, list[np.ndarray]] = {}
        self._model_version: str = ""
        self._last_optimize_at = 0.0
        self._person_cd: dict[str, tuple[float, float]] = {}  # user_id -> (until_mono, until_wall)
        self._door_cd: dict[str, tuple[float, float]] = {}
        self._dash_cache: dict[str, Any] | None = None
        self._dash_cache_at = 0.0
        self._dash_ttl = 60.0
        self._stats_cache: dict[str, Any] | None = None
        self._stats_cache_at = 0.0
        integrity = self._conn.execute("PRAGMA quick_check").fetchone()
        self.integrity_ok = True
        if integrity and str(integrity[0]).lower() != "ok":
            self.integrity_ok = False
        self._rebase_cooldowns()
        self.reload_memory()

    def _migrate(self) -> None:
        cols = {str(r[1]) for r in self._conn.execute("PRAGMA table_info(persons)").fetchall()}
        if "ha_person_entity" not in cols:
            self._conn.execute(
                "ALTER TABLE persons ADD COLUMN ha_person_entity TEXT NOT NULL DEFAULT ''"
            )
        if "person_kind" not in cols:
            self._conn.execute(
                "ALTER TABLE persons ADD COLUMN person_kind TEXT NOT NULL DEFAULT 'staff'"
            )
        if "valid_until" not in cols:
            self._conn.execute("ALTER TABLE persons ADD COLUMN valid_until REAL")
        if "allowed_spaces" not in cols:
            self._conn.execute(
                "ALTER TABLE persons ADD COLUMN allowed_spaces TEXT NOT NULL DEFAULT ''"
            )
        for col, ddl in (
            ("origin", "TEXT NOT NULL DEFAULT 'office'"),
            ("linked_user_id", "TEXT NOT NULL DEFAULT ''"),
            ("first_seen_at", "REAL"),
            ("last_seen_at", "REAL"),
            ("visit_count", "INTEGER NOT NULL DEFAULT 0"),
            ("sighted", "INTEGER NOT NULL DEFAULT 0"),
            ("notes", "TEXT NOT NULL DEFAULT ''"),
            ("phone", "TEXT NOT NULL DEFAULT ''"),
            ("ignored", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE persons ADD COLUMN {col} {ddl}")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              space_id TEXT NOT NULL DEFAULT '',
              camera TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL DEFAULT 'sight',
              similarity REAL NOT NULL DEFAULT 0,
              detail TEXT,
              created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_visits_user ON visits(user_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_visits_created ON visits(created_at)")
        space_cols = {str(r[1]) for r in self._conn.execute("PRAGMA table_info(spaces)").fetchall()}
        for col, ddl in (
            ("zones", "TEXT NOT NULL DEFAULT '[]'"),
            ("motion_masks", "TEXT NOT NULL DEFAULT '[]'"),
            ("object_masks", "TEXT NOT NULL DEFAULT '[]'"),
            ("motion_cfg", "TEXT NOT NULL DEFAULT '{}'"),
            ("track_cfg", "TEXT NOT NULL DEFAULT '{}'"),
            ("audio_cfg", "TEXT NOT NULL DEFAULT '{}'"),
            ("access_mode", "TEXT NOT NULL DEFAULT 'face'"),
            ("scene_ids", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if col not in space_cols:
                self._conn.execute(f"ALTER TABLE spaces ADD COLUMN {col} {ddl}")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scenes (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL DEFAULT 'classroom',
              adapter TEXT NOT NULL DEFAULT '',
              space_ids TEXT NOT NULL DEFAULT '[]',
              enabled INTEGER NOT NULL DEFAULT 1,
              updated_at REAL NOT NULL
            )
            """
        )

    def _invalidate_cache(self) -> None:
        self._dash_cache = None
        self._dash_cache_at = 0.0
        self._stats_cache = None
        self._stats_cache_at = 0.0

    def _person_from_row(self, r: sqlite3.Row) -> PersonRow:
        keys = r.keys()
        vu = None
        if "valid_until" in keys and r["valid_until"] is not None:
            vu = float(r["valid_until"])
        def _f(name: str, default=None):
            if name not in keys or r[name] is None:
                return default
            return r[name]

        return PersonRow(
            user_id=r["user_id"],
            display_name=r["display_name"],
            face_status=r["face_status"],
            enabled=bool(r["enabled"]),
            verify_ok_count=int(r["verify_ok_count"]),
            verify_fail_streak=int(r["verify_fail_streak"]),
            updated_at=float(r["updated_at"]) if "updated_at" in keys else 0.0,
            ha_person_entity=str(r["ha_person_entity"] or "") if "ha_person_entity" in keys else "",
            person_kind=str(r["person_kind"] or "staff") if "person_kind" in keys else "staff",
            valid_until=vu,
            allowed_spaces=str(r["allowed_spaces"] or "") if "allowed_spaces" in keys else "",
            origin=str(_f("origin", "office") or "office"),
            linked_user_id=str(_f("linked_user_id", "") or ""),
            first_seen_at=float(_f("first_seen_at")) if _f("first_seen_at") is not None else None,
            last_seen_at=float(_f("last_seen_at")) if _f("last_seen_at") is not None else None,
            visit_count=int(_f("visit_count", 0) or 0),
            sighted=bool(int(_f("sighted", 0) or 0)),
            notes=str(_f("notes", "") or ""),
            phone=str(_f("phone", "") or ""),
            ignored=bool(int(_f("ignored", 0) or 0)),
        )

    def _rebase_cooldowns(self) -> None:
        """进程重启后单调钟归零：用 wall 时钟把未过期冷却映射回当前 mono；热路径用内存。"""
        now_wall = time.time()
        now_mono = time.monotonic()
        self._person_cd.clear()
        self._door_cd.clear()
        rows = self._conn.execute("SELECT user_id, until_wall FROM cooldowns").fetchall()
        for r in rows:
            remain = float(r["until_wall"]) - now_wall
            if remain <= 0:
                self._conn.execute("DELETE FROM cooldowns WHERE user_id=?", (r["user_id"],))
            else:
                until_m = now_mono + remain
                until_w = now_wall + remain
                self._conn.execute(
                    "UPDATE cooldowns SET until_mono=? WHERE user_id=?",
                    (until_m, r["user_id"]),
                )
                self._person_cd[str(r["user_id"])] = (until_m, until_w)
        door_rows = self._conn.execute("SELECT door, until_wall FROM door_cooldowns").fetchall()
        for r in door_rows:
            remain = float(r["until_wall"]) - now_wall
            if remain <= 0:
                self._conn.execute("DELETE FROM door_cooldowns WHERE door=?", (r["door"],))
            else:
                until_m = now_mono + remain
                until_w = now_wall + remain
                self._conn.execute(
                    "UPDATE door_cooldowns SET until_mono=? WHERE door=?",
                    (until_m, r["door"]),
                )
                self._door_cd[str(r["door"])] = (until_m, until_w)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def reload_memory(self, model_version: str | None = None) -> None:
        mv = model_version
        self._mem.clear()
        # 含陌生人：再识别要关联，但不等于可开门（开门由 face_status+kind 另判）
        # ignored 仍留在底库作负锚（对齐 FaceID）：能再识别，但不告警/不开门
        q = (
            "SELECT user_id, model_version, vector FROM embeddings e "
            "JOIN persons p USING(user_id) "
            "WHERE p.enabled=1 AND p.face_status IN ('accepted','verified','pending')"
        )
        rows = self._conn.execute(q).fetchall()
        for r in rows:
            if mv and r["model_version"] != mv:
                continue
            vec = np.frombuffer(r["vector"], dtype=np.float32).copy()
            self._mem.setdefault(r["user_id"], []).append(vec)
        if mv:
            self._model_version = mv
        elif rows:
            self._model_version = rows[0]["model_version"]

    def memory_vectors(self) -> dict[str, list[np.ndarray]]:
        return self._mem

    def get_person(self, user_id: str) -> PersonRow | None:
        r = self._conn.execute("SELECT * FROM persons WHERE user_id=?", (user_id,)).fetchone()
        if not r:
            return None
        return self._person_from_row(r)

    def list_persons(self, *, scope: str = "all", limit: int | None = None) -> list[PersonRow]:
        """scope: all|sighted|credential|stranger — credential=仅预约凭证未造访。"""
        where = ""
        if scope == "sighted":
            where = "WHERE sighted=1 OR visit_count>0"
        elif scope == "credential":
            where = "WHERE (sighted=0 OR sighted IS NULL) AND visit_count=0 AND person_kind!='stranger'"
        elif scope == "stranger":
            where = "WHERE person_kind='stranger'"
        sql = f"SELECT * FROM persons {where} ORDER BY COALESCE(last_seen_at, updated_at) DESC"
        if limit is not None:
            sql += f" LIMIT {int(max(1, limit))}"
        rows = self._conn.execute(sql).fetchall()
        return [self._person_from_row(r) for r in rows]

    def search_persons(self, q: str, limit: int = 30, *, scope: str = "all") -> list[PersonRow]:
        q = (q or "").strip()
        if not q:
            return self.list_persons(scope=scope, limit=limit)
        like = f"%{q}%"
        scope_sql = ""
        if scope == "sighted":
            scope_sql = "AND (sighted=1 OR visit_count>0)"
        elif scope == "credential":
            scope_sql = "AND (sighted=0 OR sighted IS NULL) AND visit_count=0 AND person_kind!='stranger'"
        elif scope == "stranger":
            scope_sql = "AND person_kind='stranger'"
        rows = self._conn.execute(
            f"""
            SELECT * FROM persons
            WHERE (user_id LIKE ? OR display_name LIKE ?) {scope_sql}
            ORDER BY
              CASE WHEN face_status='pending' THEN 0 ELSE 1 END,
              COALESCE(last_seen_at, updated_at) DESC
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        return [self._person_from_row(r) for r in rows]

    def delete_person(self, user_id: str) -> bool:
        paths = self.frame_paths_for_user(user_id)
        cur = self._conn.cursor()
        cur.execute("BEGIN")
        try:
            cur.execute("DELETE FROM visits WHERE user_id=?", (user_id,))
            cur.execute("DELETE FROM embeddings WHERE user_id=?", (user_id,))
            cur.execute("DELETE FROM cooldowns WHERE user_id=?", (user_id,))
            cur.execute("DELETE FROM persons WHERE user_id=?", (user_id,))
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        for fp in paths:
            try:
                Path(fp).unlink(missing_ok=True)
            except Exception:
                pass
        self.reload_memory(self._model_version or None)
        return True

    def set_door_cooldown(self, door: str, until_mono: float, until_wall: float) -> None:
        self._door_cd[door] = (until_mono, until_wall)
        self._conn.execute(
            """
            INSERT INTO door_cooldowns(door, until_mono, until_wall) VALUES(?,?,?)
            ON CONFLICT(door) DO UPDATE SET until_mono=excluded.until_mono, until_wall=excluded.until_wall
            """,
            (door, until_mono, until_wall),
        )
        self._conn.commit()

    def door_cooldown_active(self, door: str, now_mono: float) -> bool:
        mem = self._door_cd.get(door)
        if mem:
            until_m, until_w = mem
            if until_w > time.time() or until_m > now_mono:
                return True
            self._door_cd.pop(door, None)
            return False
        r = self._conn.execute(
            "SELECT until_mono, until_wall FROM door_cooldowns WHERE door=?",
            (door,),
        ).fetchone()
        if not r:
            return False
        if float(r["until_wall"]) > time.time() or float(r["until_mono"]) > now_mono:
            self._door_cd[door] = (float(r["until_mono"]), float(r["until_wall"]))
            return True
        return False

    def log_access(
        self,
        *,
        source: str,
        door: str,
        user_id: str | None,
        display_name: str,
        result: str,
        reason: str,
        command_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO access_ledger(
              source, door, user_id, display_name, result, reason, command_id, detail, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                source,
                door,
                user_id,
                display_name or "",
                result,
                reason,
                command_id,
                json.dumps(detail or {}, ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()

    def list_access_ledger(
        self,
        limit: int = 50,
        result: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if result:
            clauses.append("result=?")
            args.append(result)
        if source:
            clauses.append("source=?")
            args.append(source)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT id, source, door, user_id, display_name, result, reason, command_id, detail, created_at
            FROM access_ledger {where}
            ORDER BY id DESC LIMIT ?
            """,
            args,
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except Exception:
                detail = {}
            out.append(
                {
                    "id": int(r["id"]),
                    "source": r["source"],
                    "door": r["door"],
                    "user_id": r["user_id"],
                    "display_name": r["display_name"],
                    "result": r["result"],
                    "reason": r["reason"],
                    "command_id": r["command_id"],
                    "detail": detail,
                    "created_at": float(r["created_at"]),
                }
            )
        return out

    def prune_access_ledger(self, max_rows: int = 5000, max_age_days: float = 30.0) -> dict[str, int]:
        deleted = 0
        now = time.time()
        if max_age_days > 0:
            cutoff = now - max_age_days * 86400.0
            cur = self._conn.execute("DELETE FROM access_ledger WHERE created_at < ?", (cutoff,))
            deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        if max_rows > 0:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM access_ledger").fetchone()
            total = int(row["c"] if row else 0)
            if total > max_rows:
                overflow = total - max_rows
                cur = self._conn.execute(
                    """
                    DELETE FROM access_ledger WHERE id IN (
                      SELECT id FROM access_ledger ORDER BY id ASC LIMIT ?
                    )
                    """,
                    (overflow,),
                )
                deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        self._conn.commit()
        left = int(self._conn.execute("SELECT COUNT(*) AS c FROM access_ledger").fetchone()["c"])
        return {"deleted": deleted, "remaining": left}

    def list_audit(
        self,
        limit: int = 50,
        decision: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if decision:
            clauses.append("decision=?")
            args.append(decision)
        if user_id:
            clauses.append("user_id=?")
            args.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM match_audit {where} ORDER BY id DESC LIMIT ?",
            args,
        ).fetchall()
        out = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except Exception:
                detail = {}
            out.append(
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "camera": r["camera"],
                    "similarity": r["similarity"],
                    "decision": r["decision"],
                    "detail": detail,
                    "created_at": r["created_at"],
                }
            )
        return out

    def upsert_person(
        self,
        user_id: str,
        display_name: str,
        face_status: str,
        enabled: bool = True,
        *,
        person_kind: str | None = None,
        origin: str | None = None,
    ) -> None:
        now = time.time()
        kind = person_kind or "staff"
        org = origin or "office"
        self._conn.execute(
            """
            INSERT INTO persons(
              user_id, display_name, face_status, enabled, verify_ok_count, verify_fail_streak,
              updated_at, person_kind, origin, sighted, visit_count
            )
            VALUES(?,?,?,?,0,0,?,?,?,0,0)
            ON CONFLICT(user_id) DO UPDATE SET
              display_name=excluded.display_name,
              face_status=excluded.face_status,
              enabled=excluded.enabled,
              updated_at=excluded.updated_at,
              person_kind=COALESCE(?, person_kind),
              origin=COALESCE(?, origin)
            """,
            (
                user_id,
                display_name,
                face_status,
                1 if enabled else 0,
                now,
                kind,
                org,
                person_kind,
                origin,
            ),
        )
        self._conn.commit()

    def set_status(self, user_id: str, face_status: str) -> None:
        self._conn.execute(
            "UPDATE persons SET face_status=?, updated_at=? WHERE user_id=?",
            (face_status, time.time(), user_id),
        )
        self._conn.commit()

    def set_enabled(self, user_id: str, enabled: bool) -> None:
        self._conn.execute(
            "UPDATE persons SET enabled=?, updated_at=? WHERE user_id=?",
            (1 if enabled else 0, time.time(), user_id),
        )
        self._conn.commit()
        self.reload_memory(self._model_version or None)

    def commit_enrollment(
        self,
        user_id: str,
        display_name: str,
        model_version: str,
        vectors: Iterable[np.ndarray],
        frame_paths: Iterable[str | None],
        *,
        person_kind: str | None = None,
        origin: str | None = None,
        mark_sighted: bool = False,
    ) -> None:
        """一次事务写入底库；中途失败不留下半套向量。
        origin=booking 表示预约平台录入凭证，不代表已造访办公室。
        """
        now = time.time()
        existing = self.get_person(user_id)
        kind = person_kind or (existing.person_kind if existing else "staff")
        org = origin or (existing.origin if existing else "office")
        sighted = 1 if mark_sighted or (existing and existing.sighted) else 0
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                """
                INSERT INTO persons(
                  user_id, display_name, face_status, enabled, verify_ok_count, verify_fail_streak,
                  updated_at, person_kind, origin, sighted, visit_count
                )
                VALUES(?,?, 'accepted', 1, 0, 0, ?,?,?,?,0)
                ON CONFLICT(user_id) DO UPDATE SET
                  display_name=excluded.display_name,
                  face_status='accepted',
                  enabled=1,
                  verify_ok_count=0,
                  verify_fail_streak=0,
                  updated_at=excluded.updated_at,
                  person_kind=excluded.person_kind,
                  origin=excluded.origin,
                  sighted=excluded.sighted
                """,
                (user_id, display_name, now, kind, org, sighted),
            )
            cur.execute("DELETE FROM embeddings WHERE user_id=?", (user_id,))
            for vec, path in zip(vectors, frame_paths, strict=False):
                arr = np.asarray(vec, dtype=np.float32).reshape(-1)
                cur.execute(
                    "INSERT INTO embeddings(user_id, model_version, dim, vector, frame_path, created_at) VALUES(?,?,?,?,?,?)",
                    (user_id, model_version, int(arr.size), arr.tobytes(), path, now),
                )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        self.reload_memory(model_version)
        self._invalidate_cache()

    def bump_verify(self, user_id: str, ok: bool, need: int = 3) -> str:
        p = self.get_person(user_id)
        if not p:
            return "none"
        if ok:
            ok_c = p.verify_ok_count + 1
            fail = 0
            status = "verified" if ok_c >= need else p.face_status
            if status == "accepted" and ok_c < need:
                status = "accepted"
            self._conn.execute(
                "UPDATE persons SET verify_ok_count=?, verify_fail_streak=?, face_status=?, updated_at=? WHERE user_id=?",
                (ok_c, fail, status, time.time(), user_id),
            )
        else:
            fail = p.verify_fail_streak + 1
            status = "pending" if fail >= need else p.face_status
            self._conn.execute(
                "UPDATE persons SET verify_fail_streak=?, face_status=?, updated_at=? WHERE user_id=?",
                (fail, status, time.time(), user_id),
            )
            if status == "pending":
                self._conn.execute("UPDATE persons SET enabled=1 WHERE user_id=?", (user_id,))
        self._conn.commit()
        if status == "pending":
            self.reload_memory(self._model_version or None)
        return status

    # --- cooldown (memory-first; persisted for restart) ---
    def clear_cooldown(self, user_id: str) -> None:
        self._person_cd.pop(user_id, None)
        self._conn.execute("DELETE FROM cooldowns WHERE user_id=?", (user_id,))
        self._conn.commit()

    def set_cooldown(self, user_id: str, until_mono: float, until_wall: float) -> None:
        self._person_cd[user_id] = (until_mono, until_wall)
        self._conn.execute(
            """
            INSERT INTO cooldowns(user_id, until_mono, until_wall) VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET until_mono=excluded.until_mono, until_wall=excluded.until_wall
            """,
            (user_id, until_mono, until_wall),
        )
        self._conn.commit()

    def cooldown_active(self, user_id: str, now_mono: float) -> bool:
        mem = self._person_cd.get(user_id)
        if mem:
            until_m, until_w = mem
            if until_w > time.time() or until_m > now_mono:
                return True
            self._person_cd.pop(user_id, None)
            return False
        r = self._conn.execute(
            "SELECT until_mono, until_wall FROM cooldowns WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not r:
            return False
        if float(r["until_wall"]) > time.time() or float(r["until_mono"]) > now_mono:
            self._person_cd[user_id] = (float(r["until_mono"]), float(r["until_wall"]))
            return True
        return False

    def mark_grant(self, command_id: str) -> bool:
        """返回 True 表示首次见到该 command_id。"""
        try:
            self._conn.execute(
                "INSERT INTO grants_seen(command_id, created_at) VALUES(?,?)",
                (command_id, time.time()),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def commit_grant_success(
        self,
        *,
        command_id: str,
        door: str,
        until_mono: float,
        until_wall: float,
        source: str,
        user_id: str | None,
        display_name: str,
        reason: str,
        detail: dict[str, Any] | None = None,
    ) -> bool:
        """一次 grant 成功：去重+门冷却+ledger 单事务。返回 False 表示 command_id 重复。"""
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "INSERT INTO grants_seen(command_id, created_at) VALUES(?,?)",
                    (command_id, time.time()),
                )
            except sqlite3.IntegrityError:
                cur.execute("ROLLBACK")
                return False
            cur.execute(
                """
                INSERT INTO door_cooldowns(door, until_mono, until_wall) VALUES(?,?,?)
                ON CONFLICT(door) DO UPDATE SET until_mono=excluded.until_mono, until_wall=excluded.until_wall
                """,
                (door, until_mono, until_wall),
            )
            cur.execute(
                """
                INSERT INTO access_ledger(
                  source, door, user_id, display_name, result, reason, command_id, detail, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    source,
                    door,
                    user_id,
                    display_name or "",
                    "grant",
                    reason,
                    command_id,
                    json.dumps(detail or {}, ensure_ascii=False),
                    time.time(),
                ),
            )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        self._door_cd[door] = (until_mono, until_wall)
        self._invalidate_cache()
        return True

    def audit(self, user_id: str | None, camera: str, similarity: float, decision: str, detail: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO match_audit(user_id, camera, similarity, decision, detail, created_at) VALUES(?,?,?,?,?,?)",
            (user_id, camera, similarity, decision, json.dumps(detail, ensure_ascii=False), time.time()),
        )
        self._conn.commit()

    def prune_audit(self, max_rows: int = 5000, max_age_days: float = 30.0) -> dict[str, int]:
        """按条数上限 + 年龄双轨裁剪开门审计。"""
        deleted = 0
        now = time.time()
        if max_age_days > 0:
            cutoff = now - max_age_days * 86400.0
            cur = self._conn.execute("DELETE FROM match_audit WHERE created_at < ?", (cutoff,))
            deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        if max_rows > 0:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM match_audit").fetchone()
            total = int(row["c"] if row else 0)
            if total > max_rows:
                # 保留最新 max_rows：删掉更旧的
                overflow = total - max_rows
                cur = self._conn.execute(
                    """
                    DELETE FROM match_audit WHERE id IN (
                      SELECT id FROM match_audit ORDER BY id ASC LIMIT ?
                    )
                    """,
                    (overflow,),
                )
                deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        self._conn.commit()
        left = int(self._conn.execute("SELECT COUNT(*) AS c FROM match_audit").fetchone()["c"])
        return {"deleted": deleted, "remaining": left}

    def prune_grants_seen(self, max_age_hours: float = 48.0) -> int:
        """command_id 去重只需短期窗口，过期即可删。"""
        cutoff = time.time() - max(1.0, max_age_hours) * 3600.0
        cur = self._conn.execute("DELETE FROM grants_seen WHERE created_at < ?", (cutoff,))
        self._conn.commit()
        return int(cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0)

    def prune_expired_cooldowns(self) -> int:
        now_wall = time.time()
        now_mono = time.monotonic()
        cur = self._conn.execute(
            "DELETE FROM cooldowns WHERE until_wall <= ? AND until_mono <= ?",
            (now_wall, now_mono),
        )
        n = int(cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0)
        cur2 = self._conn.execute(
            "DELETE FROM door_cooldowns WHERE until_wall <= ? AND until_mono <= ?",
            (now_wall, now_mono),
        )
        n += int(cur2.rowcount if cur2.rowcount and cur2.rowcount > 0 else 0)
        self._conn.commit()
        return n

    def all_frame_paths(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT frame_path FROM embeddings WHERE frame_path IS NOT NULL AND frame_path != ''"
        ).fetchall()
        return {str(r["frame_path"]) for r in rows if r["frame_path"]}

    def maybe_optimize(self, min_interval_sec: float = 6 * 3600.0) -> bool:
        """低频 PRAGMA optimize（非全量 VACUUM，避免长时间锁库）。"""
        now = time.time()
        if now - self._last_optimize_at < min_interval_sec:
            return False
        try:
            self._conn.execute("PRAGMA optimize")
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.commit()
            self._last_optimize_at = now
            return True
        except Exception:
            return False

    def stats(self) -> dict[str, Any]:
        now = time.time()
        if self._stats_cache is not None and now - self._stats_cache_at < self._dash_ttl:
            return dict(self._stats_cache)

        def _count(table: str) -> int:
            return int(self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])

        db_bytes = self.db_path.stat().st_size if self.db_path.is_file() else 0
        wal = self.db_path.with_suffix(self.db_path.suffix + "-wal")
        wal_bytes = wal.stat().st_size if wal.is_file() else 0
        out = {
            "persons": _count("persons"),
            "embeddings": _count("embeddings"),
            "match_audit": _count("match_audit"),
            "access_ledger": _count("access_ledger"),
            "visits": _count("visits"),
            "alerts": _count("alerts"),
            "spaces": _count("spaces"),
            "assets": _count("assets"),
            "grants_seen": _count("grants_seen"),
            "cooldowns": _count("cooldowns"),
            "db_bytes": db_bytes,
            "wal_bytes": wal_bytes,
        }
        self._stats_cache = out
        self._stats_cache_at = now
        return dict(out)

    def dashboard(self) -> dict[str, Any]:
        """工作台概览：底库分布 + 开门统计 + 待办队列（60s 缓存）。"""
        now = time.time()
        if self._dash_cache is not None and now - self._dash_cache_at < self._dash_ttl:
            return dict(self._dash_cache)
        by_status: dict[str, int] = {}
        for r in self._conn.execute(
            "SELECT face_status, COUNT(*) AS c FROM persons GROUP BY face_status"
        ).fetchall():
            by_status[str(r["face_status"])] = int(r["c"])
        total = sum(by_status.values())
        enabled = int(
            self._conn.execute(
                """
                SELECT COUNT(*) AS c FROM persons
                WHERE enabled=1 AND face_status IN ('accepted','verified')
                  AND person_kind != 'stranger'
                """
            ).fetchone()["c"]
        )
        sighted_n = int(
            self._conn.execute(
                "SELECT COUNT(*) AS c FROM persons WHERE sighted=1 OR visit_count>0"
            ).fetchone()["c"]
        )
        stranger_n = int(
            self._conn.execute(
                "SELECT COUNT(*) AS c FROM persons WHERE person_kind='stranger'"
            ).fetchone()["c"]
        )
        credential_only = int(
            self._conn.execute(
                """
                SELECT COUNT(*) AS c FROM persons
                WHERE person_kind!='stranger' AND (sighted=0 OR sighted IS NULL) AND visit_count=0
                """
            ).fetchone()["c"]
        )
        visits_h24 = int(
            self._conn.execute(
                "SELECT COUNT(*) AS c FROM visits WHERE created_at >= ?",
                (now - 86400,),
            ).fetchone()["c"]
        )
        pending = [
            {
                "user_id": r["user_id"],
                "display_name": r["display_name"],
                "face_status": r["face_status"],
                "updated_at": r["updated_at"],
            }
            for r in self._conn.execute(
                """
                SELECT user_id, display_name, face_status, updated_at FROM persons
                WHERE face_status='pending'
                ORDER BY updated_at DESC LIMIT 20
                """
            ).fetchall()
        ]
        now = time.time()

        def _match_decisions(since: float) -> dict[str, int]:
            out = {"grant": 0, "deny": 0, "skip": 0}
            for r in self._conn.execute(
                """
                SELECT decision, COUNT(*) AS c FROM match_audit
                WHERE created_at >= ? GROUP BY decision
                """,
                (since,),
            ).fetchall():
                k = str(r["decision"])
                if k in out:
                    out[k] = int(r["c"])
            return out

        def _ledger(since: float) -> dict[str, Any]:
            by_result = {"grant": 0, "drop": 0}
            by_source: dict[str, int] = {}
            for r in self._conn.execute(
                """
                SELECT result, COUNT(*) AS c FROM access_ledger
                WHERE created_at >= ? GROUP BY result
                """,
                (since,),
            ).fetchall():
                k = str(r["result"])
                if k in by_result:
                    by_result[k] = int(r["c"])
            for r in self._conn.execute(
                """
                SELECT source, COUNT(*) AS c FROM access_ledger
                WHERE created_at >= ? AND result='grant' GROUP BY source
                """,
                (since,),
            ).fetchall():
                by_source[str(r["source"])] = int(r["c"])
            return {**by_result, "by_source": by_source}

        top_grant = [
            {"user_id": r["user_id"], "n": int(r["c"])}
            for r in self._conn.execute(
                """
                SELECT user_id, COUNT(*) AS c FROM access_ledger
                WHERE result='grant' AND created_at >= ? AND user_id IS NOT NULL
                GROUP BY user_id ORDER BY c DESC LIMIT 8
                """,
                (now - 7 * 86400,),
            ).fetchall()
        ]
        # 旧库尚无 ledger 时，今日开门仍可从 match_audit.grant 回退
        h24_ledger = _ledger(now - 86400)
        d7_ledger = _ledger(now - 7 * 86400)
        h24_match = _match_decisions(now - 86400)
        d7_match = _match_decisions(now - 7 * 86400)
        if h24_ledger["grant"] == 0 and h24_match["grant"] > 0:
            h24_ledger["grant"] = h24_match["grant"]
            h24_ledger["by_source"] = {"face_match": h24_match["grant"]}
        if d7_ledger["grant"] == 0 and d7_match["grant"] > 0:
            d7_ledger["grant"] = d7_match["grant"]
            d7_ledger["by_source"] = {"face_match": d7_match["grant"]}
        open_alerts = int(
            self._conn.execute("SELECT COUNT(*) AS c FROM alerts WHERE acked=0").fetchone()["c"]
        )
        occupied = int(
            self._conn.execute("SELECT COUNT(*) AS c FROM spaces WHERE person_count > 0.1").fetchone()["c"]
        )
        armed_n = int(
            self._conn.execute(
                "SELECT COUNT(*) AS c FROM spaces WHERE armed=1 OR arm_override=1"
            ).fetchone()["c"]
        )
        visitors_expiring = [
            {
                "user_id": r["user_id"],
                "display_name": r["display_name"],
                "valid_until": float(r["valid_until"]),
            }
            for r in self._conn.execute(
                """
                SELECT user_id, display_name, valid_until FROM persons
                WHERE person_kind='visitor' AND valid_until IS NOT NULL
                  AND valid_until > ? AND valid_until < ?
                ORDER BY valid_until ASC LIMIT 20
                """,
                (now, now + 7 * 86400),
            ).fetchall()
        ]
        result = {
            "persons": {
                "total": total,
                "enabled_door": enabled,
                "sighted": sighted_n,
                "strangers": stranger_n,
                "credential_only": credential_only,
                "visits_h24": visits_h24,
                "by_status": by_status,
                "pending_recollect": pending,
            },
            "access": {
                "h24": {
                    "grant": h24_ledger["grant"],
                    "drop": h24_ledger["drop"],
                    "deny": h24_match["deny"],
                    "skip": h24_match["skip"],
                    "by_source": h24_ledger.get("by_source") or {},
                },
                "d7": {
                    "grant": d7_ledger["grant"],
                    "drop": d7_ledger["drop"],
                    "deny": d7_match["deny"],
                    "skip": d7_match["skip"],
                    "by_source": d7_ledger.get("by_source") or {},
                },
                "top_grant_7d": top_grant,
            },
            "office": {
                "open_alerts": open_alerts,
                "occupied_spaces": occupied,
                "armed_spaces": armed_n,
                "visitors_expiring": visitors_expiring,
            },
            "store": self.stats(),
        }
        self._dash_cache = result
        self._dash_cache_at = now
        return dict(result)

    def set_display_name(self, user_id: str, display_name: str) -> None:
        self._conn.execute(
            "UPDATE persons SET display_name=?, updated_at=? WHERE user_id=?",
            (display_name, time.time(), user_id),
        )
        self._conn.commit()

    def create_person(
        self,
        *,
        user_id: str | None = None,
        display_name: str = "",
        person_kind: str = "staff",
        origin: str = "manual",
        notes: str = "",
        phone: str = "",
        enabled: bool = True,
        valid_until: float | None = None,
        allowed_spaces: str = "",
    ) -> PersonRow:
        """手动建档（可不经监控识别）；对齐 FaceID / Azure：显式录入身份再挂人脸。"""
        import re
        import uuid

        kind = person_kind if person_kind in ("staff", "student", "visitor", "stranger") else "staff"
        org = origin if origin in ("office", "booking", "manual") else "manual"
        uid = (user_id or "").strip()
        if not uid:
            slug = re.sub(r"[^a-zA-Z0-9]+", "", (display_name or "person").lower())[:12] or "person"
            uid = f"manual_{slug}_{uuid.uuid4().hex[:6]}"
        if self.get_person(uid):
            raise ValueError("user_exists")
        now = time.time()
        name = (display_name or "").strip() or uid
        self._conn.execute(
            """
            INSERT INTO persons(
              user_id, display_name, face_status, enabled, verify_ok_count, verify_fail_streak,
              updated_at, person_kind, origin, sighted, visit_count, notes, phone, ignored,
              valid_until, allowed_spaces
            ) VALUES(?,?, 'none', ?, 0, 0, ?, ?, ?, 0, 0, ?, ?, 0, ?, ?)
            """,
            (
                uid,
                name,
                1 if enabled else 0,
                now,
                kind,
                org,
                notes or "",
                phone or "",
                valid_until,
                allowed_spaces or "",
            ),
        )
        self._conn.commit()
        self._invalidate_cache()
        p = self.get_person(uid)
        assert p is not None
        return p

    def update_person(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        person_kind: str | None = None,
        notes: str | None = None,
        phone: str | None = None,
        ignored: bool | None = None,
        enabled: bool | None = None,
        valid_until: float | None = None,
        set_valid_until: bool = False,
        allowed_spaces: str | None = None,
    ) -> PersonRow:
        p = self.get_person(user_id)
        if not p:
            raise KeyError("not_found")
        now = time.time()
        name = display_name if display_name is not None else p.display_name
        kind = person_kind if person_kind is not None else p.person_kind
        if kind not in ("staff", "student", "visitor", "stranger"):
            kind = p.person_kind
        nts = notes if notes is not None else p.notes
        ph = phone if phone is not None else p.phone
        ign = int(ignored) if ignored is not None else int(p.ignored)
        en = int(enabled) if enabled is not None else int(p.enabled)
        vu = valid_until if set_valid_until else p.valid_until
        spaces = allowed_spaces if allowed_spaces is not None else p.allowed_spaces
        self._conn.execute(
            """
            UPDATE persons SET
              display_name=?, person_kind=?, notes=?, phone=?, ignored=?, enabled=?,
              valid_until=?, allowed_spaces=?, updated_at=?
            WHERE user_id=?
            """,
            (name, kind, nts, ph, ign, en, vu, spaces, now, user_id),
        )
        self._conn.commit()
        if ignored is not None or enabled is not None:
            self.reload_memory(self._model_version or None)
        self._invalidate_cache()
        out = self.get_person(user_id)
        assert out is not None
        return out

    def list_person_photos(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT id, frame_path, model_version, created_at
            FROM embeddings WHERE user_id=? ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "frame_path": r["frame_path"] or "",
                "model_version": r["model_version"],
                "created_at": float(r["created_at"]),
                "has_file": bool(r["frame_path"] and Path(r["frame_path"]).is_file()),
            }
            for r in rows
        ]

    def append_person_photos(
        self,
        user_id: str,
        model_version: str,
        vectors: list[np.ndarray],
        frame_paths: list[str | None],
        *,
        max_photos: int = 20,
    ) -> dict:
        """追加参考人脸（相册入库）；超限时丢掉最旧的。"""
        p = self.get_person(user_id)
        if not p:
            raise KeyError("not_found")
        now = time.time()
        cur = self._conn.cursor()
        added = 0
        removed_paths: list[str] = []
        try:
            cur.execute("BEGIN")
            for vec, path in zip(vectors, frame_paths, strict=False):
                arr = np.asarray(vec, dtype=np.float32).reshape(-1)
                cur.execute(
                    "INSERT INTO embeddings(user_id, model_version, dim, vector, frame_path, created_at) VALUES(?,?,?,?,?,?)",
                    (user_id, model_version, int(arr.size), arr.tobytes(), path, now),
                )
                added += 1
            # 超限：删最旧
            rows = cur.execute(
                "SELECT id, frame_path FROM embeddings WHERE user_id=? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
            while len(rows) > max_photos:
                old = rows.pop(0)
                cur.execute("DELETE FROM embeddings WHERE id=?", (old["id"],))
                if old["frame_path"]:
                    removed_paths.append(str(old["frame_path"]))
            status = p.face_status
            if status in ("none", "pending", "rejected") or not status:
                status = "accepted"
            cur.execute(
                "UPDATE persons SET face_status=?, enabled=1, updated_at=? WHERE user_id=?",
                (status, now, user_id),
            )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        for fp in removed_paths:
            try:
                Path(fp).unlink(missing_ok=True)
            except Exception:
                pass
        self.reload_memory(model_version)
        self._invalidate_cache()
        return {"added": added, "total": len(self.list_person_photos(user_id)), "pruned": len(removed_paths)}

    def delete_person_photo(self, user_id: str, emb_id: int) -> bool:
        row = self._conn.execute(
            "SELECT id, frame_path FROM embeddings WHERE id=? AND user_id=?",
            (emb_id, user_id),
        ).fetchone()
        if not row:
            return False
        self._conn.execute("DELETE FROM embeddings WHERE id=?", (emb_id,))
        left = int(
            self._conn.execute(
                "SELECT COUNT(*) AS c FROM embeddings WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        )
        if left == 0:
            self._conn.execute(
                "UPDATE persons SET face_status='none', updated_at=? WHERE user_id=?",
                (time.time(), user_id),
            )
        self._conn.commit()
        if row["frame_path"]:
            try:
                Path(row["frame_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        self.reload_memory(self._model_version or None)
        self._invalidate_cache()
        return True

    def online_backup(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest = dest if dest.suffix else dest.with_suffix(".sqlite3")
        with sqlite3.connect(str(dest)) as out:
            self._conn.backup(out)
        return dest

    def frame_paths_for_user(self, user_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT frame_path FROM embeddings WHERE user_id=? AND frame_path IS NOT NULL",
            (user_id,),
        ).fetchall()
        return [r["frame_path"] for r in rows if r["frame_path"]]

    # --- spaces ---
    def upsert_space(
        self,
        space_id: str,
        *,
        name: str = "",
        kind: str = "room",
        camera: str = "",
        door_node: str = "",
        polygon: list | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        poly = json.dumps(polygon if polygon is not None else [], ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO spaces(id, name, kind, camera, door_node, polygon, armed, arm_override, person_count, created_at, updated_at)
            VALUES(?,?,?,?,?,?,0,NULL,0,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=CASE WHEN excluded.name!='' THEN excluded.name ELSE spaces.name END,
              kind=excluded.kind,
              camera=CASE WHEN excluded.camera!='' THEN excluded.camera ELSE spaces.camera END,
              door_node=CASE WHEN excluded.door_node!='' THEN excluded.door_node ELSE spaces.door_node END,
              polygon=CASE WHEN excluded.polygon!='[]' THEN excluded.polygon ELSE spaces.polygon END,
              updated_at=excluded.updated_at
            """,
            (space_id, name or space_id, kind, camera, door_node, poly, now, now),
        )
        self._conn.commit()
        self._invalidate_cache()
        return self.get_space(space_id) or {}

    def get_space(self, space_id: str) -> dict[str, Any] | None:
        r = self._conn.execute("SELECT * FROM spaces WHERE id=?", (space_id,)).fetchone()
        if not r:
            return None
        return self._space_row(r)

    def find_space_by_camera(self, camera: str) -> dict[str, Any] | None:
        """摄像头 → 空间（里门/大门各绑自己的 camera + access_mode）。"""
        cam = (camera or "").strip()
        if not cam:
            return None
        r = self._conn.execute(
            "SELECT * FROM spaces WHERE camera=? ORDER BY kind LIMIT 1",
            (cam,),
        ).fetchone()
        return self._space_row(r) if r else None

    def list_spaces(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM spaces ORDER BY kind, name").fetchall()
        return [self._space_row(r) for r in rows]

    def _space_row(self, r: sqlite3.Row) -> dict[str, Any]:
        keys = r.keys()

        def _json(col: str, default):
            if col not in keys:
                return default
            try:
                return json.loads(r[col] or ( "[]" if isinstance(default, list) else "{}"))
            except Exception:
                return default

        poly = _json("polygon", [])
        zones = _json("zones", [])
        # 兼容：旧单 polygon 升成名为 door 的区域
        if poly and len(poly) >= 3 and not zones:
            zones = [{"id": "zone_main", "name": "主区域", "points": poly}]
        armed = bool(r["armed"])
        ov = r["arm_override"]
        if ov is not None:
            armed = bool(ov)
        from .detect.motion import default_motion_config
        from .detect.labels import default_audio_config, default_track_config

        raw_motion = _json("motion_cfg", {}) or {}
        raw_track = _json("track_cfg", {}) or {}
        raw_audio = _json("audio_cfg", {}) or {}
        motion_cfg = {**default_motion_config(), **raw_motion}
        track_cfg = {**default_track_config(), **raw_track}
        if "labels" in raw_track:
            track_cfg["labels"] = list(raw_track.get("labels") or track_cfg["labels"])
        if "filters" in raw_track and isinstance(raw_track["filters"], dict):
            track_cfg["filters"] = {**(default_track_config()["filters"]), **raw_track["filters"]}
        audio_cfg = {**default_audio_config(), **raw_audio}
        return {
            "id": r["id"],
            "name": r["name"],
            "kind": r["kind"],
            "camera": r["camera"],
            "door_node": r["door_node"],
            "polygon": poly if poly else (zones[0]["points"] if zones else []),
            "zones": zones,
            "motion_masks": _json("motion_masks", []),
            "object_masks": _json("object_masks", []),
            "motion_cfg": motion_cfg,
            "track_cfg": track_cfg,
            "audio_cfg": audio_cfg,
            "armed": armed,
            "arm_override": None if ov is None else bool(ov),
            "person_count": float(r["person_count"] or 0),
            "access_mode": str(r["access_mode"] if "access_mode" in keys and r["access_mode"] else "face"),
            "scene_ids": _json("scene_ids", []),
            "updated_at": float(r["updated_at"]),
        }

    def set_space_access_mode(self, space_id: str, access_mode: str) -> dict[str, Any]:
        mode = access_mode if access_mode in ("face", "schedule", "always_open", "armed_only") else "face"
        self._conn.execute(
            "UPDATE spaces SET access_mode=?, updated_at=? WHERE id=?",
            (mode, time.time(), space_id),
        )
        self._conn.commit()
        self._invalidate_cache()
        return self.get_space(space_id) or {}

    def upsert_scene(
        self,
        scene_id: str,
        *,
        name: str = "",
        kind: str = "classroom",
        adapter: str = "",
        space_ids: list[str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = time.time()
        spaces = list(space_ids or [])
        self._conn.execute(
            """
            INSERT INTO scenes(id, name, kind, adapter, space_ids, enabled, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=CASE WHEN excluded.name!='' THEN excluded.name ELSE scenes.name END,
              kind=excluded.kind,
              adapter=excluded.adapter,
              space_ids=excluded.space_ids,
              enabled=excluded.enabled,
              updated_at=excluded.updated_at
            """,
            (
                scene_id,
                name or scene_id,
                kind,
                adapter,
                json.dumps(spaces, ensure_ascii=False),
                1 if enabled else 0,
                now,
            ),
        )
        # 反写 spaces.scene_ids
        for sid in spaces:
            sp = self.get_space(sid)
            if not sp:
                continue
            ids = list(sp.get("scene_ids") or [])
            if scene_id not in ids:
                ids.append(scene_id)
                self._conn.execute(
                    "UPDATE spaces SET scene_ids=?, updated_at=? WHERE id=?",
                    (json.dumps(ids, ensure_ascii=False), now, sid),
                )
        self._conn.commit()
        self._invalidate_cache()
        return self.get_scene(scene_id) or {}

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        r = self._conn.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()
        if not r:
            return None
        try:
            space_ids = json.loads(r["space_ids"] or "[]")
        except Exception:
            space_ids = []
        return {
            "id": r["id"],
            "name": r["name"],
            "kind": r["kind"],
            "adapter": r["adapter"],
            "space_ids": space_ids,
            "enabled": bool(r["enabled"]),
            "updated_at": float(r["updated_at"]),
        }

    def list_scenes(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM scenes ORDER BY name").fetchall()
        out = []
        for r in rows:
            try:
                space_ids = json.loads(r["space_ids"] or "[]")
            except Exception:
                space_ids = []
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "kind": r["kind"],
                    "adapter": r["adapter"],
                    "space_ids": space_ids,
                    "enabled": bool(r["enabled"]),
                    "updated_at": float(r["updated_at"]),
                }
            )
        return out

    def list_spaces_for_scene(self, scene_id: str) -> list[dict[str, Any]]:
        sc = self.get_scene(scene_id)
        if not sc:
            return []
        ids = set(sc.get("space_ids") or [])
        return [s for s in self.list_spaces() if s["id"] in ids]

    def list_visits_for_spaces(self, space_ids: list[str], limit: int = 40) -> list[dict]:
        if not space_ids:
            return []
        placeholders = ",".join("?" for _ in space_ids)
        rows = self._conn.execute(
            f"""
            SELECT * FROM visits WHERE space_id IN ({placeholders})
            ORDER BY id DESC LIMIT ?
            """,
            (*space_ids, min(200, max(1, limit))),
        ).fetchall()
        out = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except Exception:
                detail = {}
            out.append(
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "space_id": r["space_id"],
                    "camera": r["camera"],
                    "kind": r["kind"],
                    "similarity": r["similarity"],
                    "detail": detail,
                    "created_at": r["created_at"],
                }
            )
        return out

    def set_space_polygon(self, space_id: str, polygon: list) -> None:
        """兼容旧 API：写入 polygon，并同步为主区域。"""
        zones = [{"id": "zone_main", "name": "主区域", "points": polygon}] if polygon else []
        self._conn.execute(
            "UPDATE spaces SET polygon=?, zones=?, updated_at=? WHERE id=?",
            (
                json.dumps(polygon, ensure_ascii=False),
                json.dumps(zones, ensure_ascii=False),
                time.time(),
                space_id,
            ),
        )
        self._conn.commit()

    def set_space_regions(
        self,
        space_id: str,
        *,
        zones: list | None = None,
        motion_masks: list | None = None,
        object_masks: list | None = None,
    ) -> dict[str, Any]:
        cur = self.get_space(space_id)
        if not cur:
            raise KeyError(space_id)
        z = zones if zones is not None else cur.get("zones") or []
        mm = motion_masks if motion_masks is not None else cur.get("motion_masks") or []
        om = object_masks if object_masks is not None else cur.get("object_masks") or []
        primary = []
        if z and isinstance(z[0], dict) and z[0].get("points"):
            primary = z[0]["points"]
        self._conn.execute(
            """
            UPDATE spaces SET zones=?, motion_masks=?, object_masks=?, polygon=?, updated_at=?
            WHERE id=?
            """,
            (
                json.dumps(z, ensure_ascii=False),
                json.dumps(mm, ensure_ascii=False),
                json.dumps(om, ensure_ascii=False),
                json.dumps(primary, ensure_ascii=False),
                time.time(),
                space_id,
            ),
        )
        self._conn.commit()
        return self.get_space(space_id) or {}

    def set_space_vision_cfg(
        self,
        space_id: str,
        *,
        motion_cfg: dict | None = None,
        track_cfg: dict | None = None,
        audio_cfg: dict | None = None,
    ) -> dict[str, Any]:
        cur = self.get_space(space_id)
        if not cur:
            raise KeyError(space_id)
        mc = {**(cur.get("motion_cfg") or {}), **(motion_cfg or {})} if motion_cfg is not None else cur.get("motion_cfg")
        tc = {**(cur.get("track_cfg") or {}), **(track_cfg or {})} if track_cfg is not None else cur.get("track_cfg")
        if track_cfg is not None and "labels" in track_cfg:
            tc["labels"] = list(track_cfg["labels"])
        if track_cfg is not None and "filters" in track_cfg:
            tc["filters"] = dict(track_cfg["filters"])
        ac = {**(cur.get("audio_cfg") or {}), **(audio_cfg or {})} if audio_cfg is not None else cur.get("audio_cfg")
        self._conn.execute(
            "UPDATE spaces SET motion_cfg=?, track_cfg=?, audio_cfg=?, updated_at=? WHERE id=?",
            (
                json.dumps(mc or {}, ensure_ascii=False),
                json.dumps(tc or {}, ensure_ascii=False),
                json.dumps(ac or {}, ensure_ascii=False),
                time.time(),
                space_id,
            ),
        )
        self._conn.commit()
        return self.get_space(space_id) or {}

    def set_space_person_count(self, space_id: str, count: float) -> None:
        self._conn.execute(
            "UPDATE spaces SET person_count=?, updated_at=? WHERE id=?",
            (float(count), time.time(), space_id),
        )
        self._conn.commit()
        self._invalidate_cache()

    def set_space_armed(self, space_id: str, armed: bool, *, override: bool | None = None) -> None:
        if override is not None:
            self._conn.execute(
                "UPDATE spaces SET arm_override=?, updated_at=? WHERE id=?",
                (1 if override else 0, time.time(), space_id),
            )
        else:
            self._conn.execute(
                "UPDATE spaces SET armed=?, arm_override=NULL, updated_at=? WHERE id=?",
                (1 if armed else 0, time.time(), space_id),
            )
        self._conn.commit()
        self._invalidate_cache()

    def ensure_default_spaces(self, door_node: str, cameras: list[str]) -> None:
        """从 options 种子门口空间；已有则不动。"""
        if self.get_space(door_node):
            return
        cam = cameras[0] if cameras else ""
        self.upsert_space(door_node, name=door_node, kind="door", camera=cam, door_node=door_node)

    # --- alerts ---
    def insert_alert(
        self,
        *,
        space_id: str,
        kind: str,
        severity: str,
        title: str,
        detail: dict[str, Any] | None = None,
        frame_path: str | None = None,
        latch_key: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO alerts(space_id, kind, severity, title, detail, frame_path, latch_key, created_at, acked)
            VALUES(?,?,?,?,?,?,?,?,0)
            """,
            (
                space_id,
                kind,
                severity,
                title,
                json.dumps(detail or {}, ensure_ascii=False),
                frame_path,
                latch_key,
                time.time(),
            ),
        )
        self._conn.commit()
        self._invalidate_cache()
        return int(cur.lastrowid)

    def list_alerts(
        self,
        *,
        limit: int = 50,
        acked: bool | None = False,
        kind: str | None = None,
        space_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if acked is not None:
            clauses.append("acked=?")
            args.append(1 if acked else 0)
        if kind:
            clauses.append("kind=?")
            args.append(kind)
        if space_id:
            clauses.append("space_id=?")
            args.append(space_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY id DESC LIMIT ?",
            args,
        ).fetchall()
        out = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except Exception:
                detail = {}
            out.append(
                {
                    "id": int(r["id"]),
                    "space_id": r["space_id"],
                    "kind": r["kind"],
                    "severity": r["severity"],
                    "title": r["title"],
                    "detail": detail,
                    "frame_path": r["frame_path"],
                    "latch_key": r["latch_key"],
                    "created_at": float(r["created_at"]),
                    "acked": bool(r["acked"]),
                }
            )
        return out

    def get_alert(self, alert_id: int) -> dict[str, Any] | None:
        r = self._conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not r:
            return None
        try:
            detail = json.loads(r["detail"] or "{}")
        except Exception:
            detail = {}
        return {
            "id": int(r["id"]),
            "space_id": r["space_id"],
            "kind": r["kind"],
            "severity": r["severity"],
            "title": r["title"],
            "detail": detail,
            "frame_path": r["frame_path"],
            "latch_key": r["latch_key"],
            "created_at": float(r["created_at"]),
            "acked": bool(r["acked"]),
        }

    def ack_alert(self, alert_id: int) -> bool:
        cur = self._conn.execute("UPDATE alerts SET acked=1 WHERE id=?", (alert_id,))
        self._conn.commit()
        self._invalidate_cache()
        return (cur.rowcount or 0) > 0

    def prune_alerts(self, max_rows: int = 5000, max_age_days: float = 30.0) -> dict[str, int]:
        deleted = 0
        now = time.time()
        if max_age_days > 0:
            cutoff = now - max_age_days * 86400.0
            cur = self._conn.execute("DELETE FROM alerts WHERE created_at < ?", (cutoff,))
            deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        if max_rows > 0:
            total = int(self._conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"])
            if total > max_rows:
                overflow = total - max_rows
                cur = self._conn.execute(
                    "DELETE FROM alerts WHERE id IN (SELECT id FROM alerts ORDER BY id ASC LIMIT ?)",
                    (overflow,),
                )
                deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        self._conn.commit()
        left = int(self._conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"])
        return {"deleted": deleted, "remaining": left}

    # --- assets / allowlist ---
    def upsert_asset(
        self,
        tag_id: str,
        *,
        name: str = "",
        space_id: str = "",
        custodian: str = "",
        status: str = "active",
    ) -> dict[str, Any]:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO assets(tag_id, name, space_id, custodian, status, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(tag_id) DO UPDATE SET
              name=excluded.name,
              space_id=excluded.space_id,
              custodian=excluded.custodian,
              status=excluded.status,
              updated_at=excluded.updated_at
            """,
            (tag_id, name or tag_id, space_id, custodian, status, now),
        )
        self._conn.commit()
        return self.get_asset(tag_id) or {}

    def get_asset(self, tag_id: str) -> dict[str, Any] | None:
        r = self._conn.execute("SELECT * FROM assets WHERE tag_id=?", (tag_id,)).fetchone()
        if not r:
            return None
        return {
            "tag_id": r["tag_id"],
            "name": r["name"],
            "space_id": r["space_id"],
            "custodian": r["custodian"],
            "status": r["status"],
            "updated_at": float(r["updated_at"]),
        }

    def list_assets(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM assets ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "tag_id": r["tag_id"],
                "name": r["name"],
                "space_id": r["space_id"],
                "custodian": r["custodian"],
                "status": r["status"],
                "updated_at": float(r["updated_at"]),
            }
            for r in rows
        ]

    def delete_asset(self, tag_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM assets WHERE tag_id=?", (tag_id,))
        self._conn.commit()
        return (cur.rowcount or 0) > 0

    def active_tags_for_room(self, space_id: str | None = None) -> list[str]:
        if space_id:
            rows = self._conn.execute(
                "SELECT tag_id FROM assets WHERE status='active' AND (space_id=? OR space_id='')",
                (space_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT tag_id FROM assets WHERE status='active'"
            ).fetchall()
        return [str(r["tag_id"]) for r in rows]

    def next_allowlist_rev(self, room: str) -> int:
        r = self._conn.execute("SELECT rev FROM allowlist_meta WHERE room=?", (room,)).fetchone()
        rev = int(r["rev"]) + 1 if r else 1
        self._conn.execute(
            """
            INSERT INTO allowlist_meta(room, rev, updated_at) VALUES(?,?,?)
            ON CONFLICT(room) DO UPDATE SET rev=excluded.rev, updated_at=excluded.updated_at
            """,
            (room, rev, time.time()),
        )
        self._conn.commit()
        return rev

    def get_allowlist_rev(self, room: str) -> int:
        r = self._conn.execute("SELECT rev FROM allowlist_meta WHERE room=?", (room,)).fetchone()
        return int(r["rev"]) if r else 0

    def mark_rfid_seen(self, event_id: str) -> bool:
        try:
            self._conn.execute(
                "INSERT INTO rfid_seen(event_id, created_at) VALUES(?,?)",
                (event_id, time.time()),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def prune_rfid_seen(self, max_age_hours: float = 48.0) -> int:
        cutoff = time.time() - max(1.0, max_age_hours) * 3600.0
        cur = self._conn.execute("DELETE FROM rfid_seen WHERE created_at < ?", (cutoff,))
        self._conn.commit()
        return int(cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0)

    # --- policy windows ---
    def upsert_policy_window(
        self,
        win_id: str,
        *,
        space_id: str,
        subject_id: str,
        subject_name: str,
        source: str,
        window_start: float,
        window_end: float,
        rev: str = "",
        raw: dict | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO policy_windows(
              id, space_id, subject_id, subject_name, source, window_start, window_end, rev, raw, pulled_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              space_id=excluded.space_id,
              subject_id=excluded.subject_id,
              subject_name=excluded.subject_name,
              source=excluded.source,
              window_start=excluded.window_start,
              window_end=excluded.window_end,
              rev=excluded.rev,
              raw=excluded.raw,
              pulled_at=excluded.pulled_at
            """,
            (
                win_id,
                space_id,
                subject_id,
                subject_name,
                source,
                window_start,
                window_end,
                rev,
                json.dumps(raw or {}, ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()

    def active_policy_windows(self, *, space_id: str | None = None, now: float | None = None) -> list[dict[str, Any]]:
        now = now if now is not None else time.time()
        if space_id:
            rows = self._conn.execute(
                """
                SELECT * FROM policy_windows
                WHERE space_id=? AND window_start <= ? AND window_end >= ?
                ORDER BY window_start ASC LIMIT 50
                """,
                (space_id, now, now),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM policy_windows
                WHERE window_start <= ? AND window_end >= ?
                ORDER BY window_start ASC LIMIT 100
                """,
                (now, now),
            ).fetchall()
        return [self._policy_row(r) for r in rows]

    def next_policy_windows(self, *, space_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        now = time.time()
        if space_id:
            rows = self._conn.execute(
                """
                SELECT * FROM policy_windows
                WHERE space_id=? AND window_end >= ?
                ORDER BY window_start ASC LIMIT ?
                """,
                (space_id, now, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM policy_windows WHERE window_end >= ?
                ORDER BY window_start ASC LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [self._policy_row(r) for r in rows]

    def _policy_row(self, r: sqlite3.Row) -> dict[str, Any]:
        try:
            raw = json.loads(r["raw"] or "{}")
        except Exception:
            raw = {}
        return {
            "id": r["id"],
            "space_id": r["space_id"],
            "subject_id": r["subject_id"],
            "subject_name": r["subject_name"],
            "source": r["source"],
            "window_start": float(r["window_start"]),
            "window_end": float(r["window_end"]),
            "rev": r["rev"],
            "raw": raw,
            "pulled_at": float(r["pulled_at"]),
        }

    def prune_policy_windows(self) -> int:
        cutoff = time.time() - 3600.0
        cur = self._conn.execute("DELETE FROM policy_windows WHERE window_end < ?", (cutoff,))
        self._conn.commit()
        return int(cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0)

    def overlapping_policy_spaces(self) -> list[str]:
        """返回当前有重叠窗口的 space_id（总览标红）。"""
        now = time.time()
        rows = self._conn.execute(
            """
            SELECT a.space_id FROM policy_windows a
            JOIN policy_windows b ON a.space_id=b.space_id AND a.id < b.id
            WHERE a.window_start < b.window_end AND b.window_start < a.window_end
              AND a.window_end >= ? AND b.window_end >= ?
            GROUP BY a.space_id
            """,
            (now, now),
        ).fetchall()
        return [str(r["space_id"]) for r in rows]

    # --- arming plans ---
    def set_arming_plan(self, space_id: str, schedule: list) -> None:
        self._conn.execute(
            """
            INSERT INTO arming_plans(space_id, schedule, updated_at) VALUES(?,?,?)
            ON CONFLICT(space_id) DO UPDATE SET schedule=excluded.schedule, updated_at=excluded.updated_at
            """,
            (space_id, json.dumps(schedule, ensure_ascii=False), time.time()),
        )
        self._conn.commit()

    def get_arming_plan(self, space_id: str) -> list:
        r = self._conn.execute(
            "SELECT schedule FROM arming_plans WHERE space_id=?",
            (space_id,),
        ).fetchone()
        if not r:
            return []
        try:
            return json.loads(r["schedule"] or "[]")
        except Exception:
            return []

    # --- visits / sightings（办公室造访事实；≠ 预约平台录入凭证）---
    def record_visit(
        self,
        user_id: str,
        *,
        camera: str = "",
        space_id: str = "",
        kind: str = "sight",
        similarity: float = 0.0,
        detail: dict | None = None,
        min_interval_sec: float = 120.0,
    ) -> int | None:
        """记一次造访；同一人短间隔去抖。返回 visit id 或 None（去抖跳过）。"""
        now = time.time()
        if min_interval_sec > 0:
            last = self._conn.execute(
                "SELECT created_at FROM visits WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if last and now - float(last["created_at"]) < min_interval_sec:
                # 仍刷新 last_seen，不计新 visit
                self._conn.execute(
                    "UPDATE persons SET last_seen_at=?, sighted=1, updated_at=? WHERE user_id=?",
                    (now, now, user_id),
                )
                self._conn.commit()
                return None
        cur = self._conn.execute(
            """
            INSERT INTO visits(user_id, space_id, camera, kind, similarity, detail, created_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                user_id,
                space_id,
                camera,
                kind,
                float(similarity),
                json.dumps(detail or {}, ensure_ascii=False),
                now,
            ),
        )
        vid = int(cur.lastrowid)
        self._conn.execute(
            """
            UPDATE persons SET
              sighted=1,
              visit_count=visit_count+1,
              first_seen_at=COALESCE(first_seen_at, ?),
              last_seen_at=?,
              updated_at=?
            WHERE user_id=?
            """,
            (now, now, now, user_id),
        )
        self._conn.commit()
        self._invalidate_cache()
        return vid

    def list_visits(self, user_id: str | None = None, limit: int = 40) -> list[dict]:
        if user_id:
            rows = self._conn.execute(
                "SELECT * FROM visits WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, min(200, max(1, limit))),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM visits ORDER BY id DESC LIMIT ?",
                (min(200, max(1, limit)),),
            ).fetchall()
        out = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except Exception:
                detail = {}
            out.append(
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "space_id": r["space_id"],
                    "camera": r["camera"],
                    "kind": r["kind"],
                    "similarity": r["similarity"],
                    "detail": detail,
                    "created_at": r["created_at"],
                }
            )
        return out

    def prune_visits(self, max_rows: int = 20000, max_age_days: int = 90) -> int:
        cutoff = time.time() - max(1, max_age_days) * 86400
        self._conn.execute("DELETE FROM visits WHERE created_at < ?", (cutoff,))
        row = self._conn.execute("SELECT COUNT(*) AS c FROM visits").fetchone()
        n = int(row["c"] if row else 0)
        deleted = 0
        if n > max_rows:
            extra = n - max_rows
            self._conn.execute(
                "DELETE FROM visits WHERE id IN (SELECT id FROM visits ORDER BY id ASC LIMIT ?)",
                (extra,),
            )
            deleted = extra
        self._conn.commit()
        return deleted

    def ingest_sighting(
        self,
        vec: np.ndarray,
        *,
        model_version: str,
        frame_path: str | None = None,
        camera: str = "",
        space_id: str = "",
        similarity: float = 0.0,
    ) -> PersonRow:
        """陌生人首次入库：建档案 + 人脸向量 + 造访记录。"""
        import uuid

        now = time.time()
        uid = f"sight_{uuid.uuid4().hex[:12]}"
        name = f"陌生人 {uid[-4:]}"
        arr = np.asarray(vec, dtype=np.float32).reshape(-1)
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute(
                """
                INSERT INTO persons(
                  user_id, display_name, face_status, enabled, verify_ok_count, verify_fail_streak,
                  updated_at, person_kind, origin, sighted, visit_count, first_seen_at, last_seen_at
                ) VALUES(?,?, 'accepted', 1, 0, 0, ?, 'stranger', 'office', 1, 1, ?, ?)
                """,
                (uid, name, now, now, now),
            )
            cur.execute(
                "INSERT INTO embeddings(user_id, model_version, dim, vector, frame_path, created_at) VALUES(?,?,?,?,?,?)",
                (uid, model_version, int(arr.size), arr.tobytes(), frame_path, now),
            )
            cur.execute(
                """
                INSERT INTO visits(user_id, space_id, camera, kind, similarity, detail, created_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    uid,
                    space_id,
                    camera,
                    "sight",
                    float(similarity),
                    json.dumps({"new": True}, ensure_ascii=False),
                    now,
                ),
            )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        self.reload_memory(model_version)
        self._invalidate_cache()
        p = self.get_person(uid)
        assert p is not None
        return p

    def link_persons(self, stranger_id: str, target_id: str) -> PersonRow:
        """将陌生人档案合并到已有身份（预约/员工等）；保留目标 id，迁移向量与造访。"""
        src = self.get_person(stranger_id)
        dst = self.get_person(target_id)
        if not src or not dst:
            raise KeyError("not_found")
        if stranger_id == target_id:
            return dst
        now = time.time()
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            cur.execute("UPDATE embeddings SET user_id=? WHERE user_id=?", (target_id, stranger_id))
            cur.execute("UPDATE visits SET user_id=? WHERE user_id=?", (target_id, stranger_id))
            cur.execute(
                "UPDATE match_audit SET user_id=? WHERE user_id=?",
                (target_id, stranger_id),
            )
            vc = cur.execute(
                "SELECT COUNT(*) AS c FROM visits WHERE user_id=?", (target_id,)
            ).fetchone()
            visit_n = int(vc["c"] if vc else 0)
            candidates = [t for t in (src.first_seen_at, dst.first_seen_at) if t is not None]
            first = min(candidates) if candidates else now
            lasts = [t for t in (src.last_seen_at, dst.last_seen_at, now) if t is not None]
            last = max(lasts) if lasts else now
            cur.execute(
                """
                UPDATE persons SET
                  sighted=1,
                  visit_count=?,
                  first_seen_at=COALESCE(first_seen_at, ?),
                  last_seen_at=?,
                  linked_user_id='',
                  updated_at=?
                WHERE user_id=?
                """,
                (visit_n, first, last, now, target_id),
            )
            cur.execute("DELETE FROM cooldowns WHERE user_id=?", (stranger_id,))
            cur.execute("DELETE FROM persons WHERE user_id=?", (stranger_id,))
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        self.reload_memory(self._model_version or None)
        self._invalidate_cache()
        p = self.get_person(target_id)
        assert p is not None
        return p

    def can_open_by_face(self, user_id: str) -> bool:
        """刷脸开门资格：非陌生人、未忽略、已启用、人脸 accepted/verified。"""
        p = self.get_person(user_id)
        if not p or not p.enabled or p.ignored:
            return False
        if p.person_kind == "stranger":
            return False
        if p.face_status not in ("accepted", "verified"):
            return False
        if p.valid_until is not None and p.valid_until < time.time():
            return False
        return True

    # --- visitors ---
    def set_person_visitor(
        self,
        user_id: str,
        *,
        person_kind: str = "visitor",
        valid_until: float | None = None,
        allowed_spaces: str = "",
    ) -> None:
        self._conn.execute(
            """
            UPDATE persons SET person_kind=?, valid_until=?, allowed_spaces=?, updated_at=?
            WHERE user_id=?
            """,
            (person_kind, valid_until, allowed_spaces, time.time(), user_id),
        )
        self._conn.commit()
        self._invalidate_cache()

    def expire_visitors(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        rows = self._conn.execute(
            """
            SELECT user_id FROM persons
            WHERE valid_until IS NOT NULL AND valid_until < ? AND enabled=1
            """,
            (now,),
        ).fetchall()
        n = 0
        for r in rows:
            self._conn.execute(
                "UPDATE persons SET enabled=0, face_status='rejected', updated_at=? WHERE user_id=?",
                (now, r["user_id"]),
            )
            n += 1
        if n:
            self._conn.commit()
            self.reload_memory(self._model_version or None)
            self._invalidate_cache()
        return n

    def person_allowed_in_space(self, user_id: str, space_id: str) -> bool:
        p = self.get_person(user_id)
        if not p or not p.enabled:
            return False
        if p.valid_until is not None and p.valid_until < time.time():
            return False
        if not p.allowed_spaces:
            return True
        allowed = {s.strip() for s in p.allowed_spaces.split(",") if s.strip()}
        return space_id in allowed

    def recent_grant_for_door(self, door: str, within_sec: float = 30.0) -> bool:
        cutoff = time.time() - within_sec
        r = self._conn.execute(
            """
            SELECT 1 FROM access_ledger
            WHERE door=? AND result='grant' AND created_at >= ? LIMIT 1
            """,
            (door, cutoff),
        ).fetchone()
        return bool(r)
