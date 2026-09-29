"""SQLite storage: catalogue tables written by the pipeline, session tables written by the agent."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS brand (
  brand_id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  country TEXT
);
CREATE TABLE IF NOT EXISTS perfume (
  perfume_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  brand_id TEXT NOT NULL REFERENCES brand(brand_id),
  brand_name TEXT NOT NULL,
  launch_year INTEGER,
  concentration TEXT,
  gender TEXT,
  family TEXT NOT NULL,
  strength INTEGER NOT NULL,
  seasons TEXT NOT NULL,      -- JSON list
  occasions TEXT NOT NULL,    -- JSON list
  moods TEXT NOT NULL,        -- JSON list
  description TEXT NOT NULL,
  description_ar TEXT NOT NULL,
  image_url TEXT,
  product_url TEXT,
  price_aed REAL,
  price_source TEXT,          -- catalogue | estimated | none
  rating REAL,
  rating_count INTEGER,
  source TEXT NOT NULL,
  licence TEXT NOT NULL,
  recommendable INTEGER NOT NULL DEFAULT 1,
  UNIQUE(brand_id, name)
);
CREATE TABLE IF NOT EXISTS note (
  note_id TEXT PRIMARY KEY,   -- master note name
  name_ar TEXT NOT NULL,
  family TEXT NOT NULL,
  synonyms TEXT NOT NULL      -- JSON list
);
CREATE TABLE IF NOT EXISTS perfume_note (
  perfume_id TEXT NOT NULL REFERENCES perfume(perfume_id) ON DELETE CASCADE,
  note_id TEXT NOT NULL,
  layer TEXT NOT NULL,        -- top | heart | base
  raw_name TEXT NOT NULL,
  PRIMARY KEY (perfume_id, note_id, layer)
);
CREATE TABLE IF NOT EXISTS perfume_accord (
  perfume_id TEXT NOT NULL REFERENCES perfume(perfume_id) ON DELETE CASCADE,
  accord TEXT NOT NULL,
  strength INTEGER NOT NULL,  -- 0..100
  PRIMARY KEY (perfume_id, accord)
);
CREATE TABLE IF NOT EXISTS layering_pair (
  perfume_a_id TEXT NOT NULL,
  perfume_b_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  reason_ar TEXT NOT NULL,
  source TEXT NOT NULL,       -- rule | expert
  PRIMARY KEY (perfume_a_id, perfume_b_id)
);
CREATE TABLE IF NOT EXISTS perfume_embedding (
  perfume_id TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  vector BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS review_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,         -- unknown_note | incomplete | zero_results | low_rating
  payload TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS session (
  session_id TEXT PRIMARY KEY,
  language TEXT NOT NULL,
  profile TEXT NOT NULL,      -- JSON taste profile
  history TEXT NOT NULL,      -- JSON list of {role, text}
  consent_wishlist INTEGER NOT NULL DEFAULT 0,
  last_results TEXT NOT NULL DEFAULT '[]',  -- JSON list of perfume ids shown
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS wishlist (
  session_id TEXT NOT NULL,
  perfume_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  PRIMARY KEY (session_id, perfume_id)
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  perfume_id TEXT NOT NULL,
  thumbs INTEGER,             -- 1 up, -1 down, NULL none
  clicked INTEGER NOT NULL DEFAULT 0,
  saved INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  name TEXT NOT NULL,
  props TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_perfume_note_note ON perfume_note(note_id);
CREATE INDEX IF NOT EXISTS idx_perfume_brand ON perfume(brand_name);
CREATE INDEX IF NOT EXISTS idx_event_name ON event(name);
CREATE TABLE IF NOT EXISTS chat_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  visitor_id TEXT,
  created_at REAL NOT NULL,
  endpoint TEXT NOT NULL,
  lang TEXT,
  user_text TEXT,
  reply_text TEXT,
  question_text TEXT,
  intent TEXT,
  picks TEXT,
  fallback_used INTEGER DEFAULT 0,
  latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chat_log_created ON chat_log(created_at);
CREATE INDEX IF NOT EXISTS idx_chat_log_session ON chat_log(session_id);
"""

_lock = threading.Lock()


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


def connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL is unreliable on SMB shares (the Azure Files mount at /data), so use rollback journaling there.
    default_mode = "DELETE" if str(db_path).startswith("/data") else "WAL"
    conn.execute(f"PRAGMA journal_mode={os.environ.get('SQLITE_JOURNAL_MODE', default_mode)}")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


class Database:
    """Thin wrapper holding one connection; SQLite serialises writes for us."""

    def __init__(self, path: str | None = None):
        self.path = path or settings.database_path
        self.conn = connect(self.path)

    @contextmanager
    def tx(self):
        with _lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    # ---- catalogue reads -------------------------------------------------
    def perfume_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM perfume").fetchone()[0]

    def all_perfumes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM perfume").fetchall()
        notes = {}
        for r in self.conn.execute("SELECT perfume_id, note_id, layer, raw_name FROM perfume_note"):
            notes.setdefault(r["perfume_id"], []).append({"note": r["note_id"], "layer": r["layer"], "raw": r["raw_name"]})
        accords = {}
        for r in self.conn.execute("SELECT perfume_id, accord, strength FROM perfume_accord"):
            accords.setdefault(r["perfume_id"], {})[r["accord"]] = r["strength"]
        out = []
        for r in rows:
            d = dict(r)
            for k in ("seasons", "occasions", "moods"):
                d[k] = json.loads(d[k])
            d["notes"] = notes.get(d["perfume_id"], [])
            d["accords"] = accords.get(d["perfume_id"], {})
            out.append(d)
        return out

    def load_embeddings(self) -> dict[str, bytes]:
        return {r["perfume_id"]: r["vector"] for r in self.conn.execute("SELECT perfume_id, vector FROM perfume_embedding")}

    # ---- sessions ---------------------------------------------------------
    def get_session(self, session_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM session WHERE session_id=?", (session_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["profile"] = json.loads(d["profile"])
        d["history"] = json.loads(d["history"])
        d["last_results"] = json.loads(d["last_results"])
        return d

    def create_session(self, language: str) -> dict:
        now = time.time()
        sid = new_id("s_")
        with self.tx() as c:
            c.execute(
                "INSERT INTO session(session_id, language, profile, history, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (sid, language, "{}", "[]", now, now),
            )
        return self.get_session(sid)

    def save_session(self, s: dict) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE session SET language=?, profile=?, history=?, consent_wishlist=?, last_results=?, updated_at=? WHERE session_id=?",
                (
                    s["language"], json.dumps(s["profile"], ensure_ascii=False),
                    json.dumps(s["history"][-30:], ensure_ascii=False), int(s.get("consent_wishlist", 0)),
                    json.dumps(s.get("last_results", [])), time.time(), s["session_id"],
                ),
            )

    def add_wishlist(self, session_id: str, perfume_ids: list[str]) -> None:
        now = time.time()
        with self.tx() as c:
            for pid in perfume_ids:
                c.execute("INSERT OR IGNORE INTO wishlist(session_id, perfume_id, created_at) VALUES (?,?,?)", (session_id, pid, now))
                c.execute("INSERT INTO feedback(session_id, perfume_id, saved, created_at) VALUES (?,?,1,?)", (session_id, pid, now))

    def get_wishlist(self, session_id: str) -> list[str]:
        return [r["perfume_id"] for r in self.conn.execute("SELECT perfume_id FROM wishlist WHERE session_id=? ORDER BY created_at", (session_id,))]

    def add_feedback(self, session_id: str, perfume_id: str, thumbs: int | None = None, clicked: bool = False) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO feedback(session_id, perfume_id, thumbs, clicked, created_at) VALUES (?,?,?,?,?)",
                (session_id, perfume_id, thumbs, int(clicked), time.time()),
            )
            if thumbs == -1:
                c.execute("INSERT INTO review_queue(kind, payload, created_at) VALUES ('low_rating', ?, ?)",
                          (json.dumps({"session_id": session_id, "perfume_id": perfume_id}), time.time()))

    def add_event(self, session_id: str | None, name: str, props: dict | None = None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO event(session_id, name, props, created_at) VALUES (?,?,?,?)",
                      (session_id, name, json.dumps(props or {}, ensure_ascii=False), time.time()))

    def add_review(self, kind: str, payload: dict) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO review_queue(kind, payload, created_at) VALUES (?,?,?)",
                      (kind, json.dumps(payload, ensure_ascii=False), time.time()))

    # ---- usage tracking ---------------------------------------------------
    def add_chat_log(self, *, session_id, visitor_id, endpoint, lang, user_text, reply_text, question_text,
                     intent, picks, fallback_used, latency_ms) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO chat_log(session_id, visitor_id, created_at, endpoint, lang, user_text, reply_text, "
                "question_text, intent, picks, fallback_used, latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, visitor_id, time.time(), endpoint, lang, (user_text or "")[:2000],
                 (reply_text or "")[:4000], (question_text or "")[:500], intent,
                 json.dumps(picks or [], ensure_ascii=False), int(bool(fallback_used)), int(latency_ms or 0)))

    @staticmethod
    def _iso(ts: float) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    def usage_summary(self, since_ts: float) -> dict:
        rows = [dict(r) for r in self.conn.execute(
            "SELECT session_id, visitor_id, created_at, endpoint, lang, user_text, intent, picks, fallback_used, "
            "latency_ms FROM chat_log WHERE created_at >= ? ORDER BY created_at", (since_ts,))]
        def is_message(r):  # something the shopper typed or tapped, not a system marker
            return bool(r["user_text"]) and not r["user_text"].startswith("[guided:")
        days: dict[str, dict] = {}
        languages: dict[str, int] = {}
        intents: dict[str, int] = {}
        for r in rows:
            d = days.setdefault(time.strftime("%Y-%m-%d", time.gmtime(r["created_at"])),
                                {"visitors": set(), "sessions": set(), "messages": 0})
            d["visitors"].add(r["visitor_id"]); d["sessions"].add(r["session_id"])
            d["messages"] += 1 if is_message(r) else 0
            languages[r["lang"] or "?"] = languages.get(r["lang"] or "?", 0) + 1
            intents[r["intent"] or "?"] = intents.get(r["intent"] or "?", 0) + 1
        lat = sorted(r["latency_ms"] for r in rows if r["latency_ms"])
        return {
            "since": self._iso(since_ts),
            "visitors": len({r["visitor_id"] for r in rows}),
            "sessions": len({r["session_id"] for r in rows}),
            "messages": sum(1 for r in rows if is_message(r)),
            "recommendations": sum(1 for r in rows if r["picks"] and r["picks"] != "[]"),
            "guided_started": sum(1 for r in rows if r["endpoint"] == "/api/guide/start"),
            "fallback_turns": sum(1 for r in rows if r["fallback_used"]),
            "median_latency_ms": lat[len(lat) // 2] if lat else None,
            "languages": languages,
            "intents": intents,
            "by_day": [{"date": k, "visitors": len(v["visitors"]), "sessions": len(v["sessions"]),
                        "messages": v["messages"]} for k, v in sorted(days.items())],
        }

    def recent_conversations(self, since_ts: float, limit: int = 50) -> list[dict]:
        sessions = [r["session_id"] for r in self.conn.execute(
            "SELECT session_id, MAX(created_at) AS last FROM chat_log WHERE created_at >= ? "
            "GROUP BY session_id ORDER BY last DESC LIMIT ?", (since_ts, limit))]
        out = []
        for sid in sessions:
            rows = [dict(r) for r in self.conn.execute(
                "SELECT * FROM chat_log WHERE session_id IS ? AND created_at >= ? ORDER BY created_at LIMIT 60",
                (sid, since_ts))]
            if not rows:
                continue
            turns = []
            for r in rows:
                try:
                    picks = [{"name": p.get("name"), "brand": p.get("brand")} for p in json.loads(r["picks"] or "[]")]
                except (ValueError, AttributeError):
                    picks = []
                turns.append({"at": self._iso(r["created_at"]), "endpoint": r["endpoint"], "user": r["user_text"],
                              "advisor": r["reply_text"], "question": r["question_text"], "intent": r["intent"],
                              "picks": picks, "fallback_used": bool(r["fallback_used"]),
                              "latency_ms": r["latency_ms"]})
            out.append({"session_id": sid, "visitor_id": rows[0]["visitor_id"],
                        "started_at": self._iso(rows[0]["created_at"]),
                        "last_active_at": self._iso(rows[-1]["created_at"]), "lang": rows[-1]["lang"],
                        "message_count": sum(1 for r in rows if r["user_text"] and not r["user_text"].startswith("[guided:")),
                        "turns": turns})
        return out

    # ---- admin ------------------------------------------------------------
    def admin_summary(self) -> dict:
        c = self.conn
        counts = {r["name"]: r["n"] for r in c.execute("SELECT name, COUNT(*) AS n FROM event GROUP BY name")}
        review = {r["kind"]: r["n"] for r in c.execute("SELECT kind, COUNT(*) AS n FROM review_queue GROUP BY kind")}
        low = [dict(r) for r in c.execute(
            "SELECT f.perfume_id, p.name, p.brand_name, COUNT(*) AS downs FROM feedback f JOIN perfume p ON p.perfume_id=f.perfume_id "
            "WHERE f.thumbs=-1 GROUP BY f.perfume_id ORDER BY downs DESC LIMIT 20")]
        zero = [json.loads(r["payload"]) for r in c.execute(
            "SELECT payload FROM review_queue WHERE kind='zero_results' ORDER BY created_at DESC LIMIT 20")]
        unknown = [json.loads(r["payload"]) for r in c.execute(
            "SELECT payload FROM review_queue WHERE kind='unknown_note' ORDER BY created_at DESC LIMIT 50")]
        thumbs = c.execute("SELECT SUM(thumbs=1) AS up, SUM(thumbs=-1) AS down FROM feedback").fetchone()
        return {
            "perfumes": self.perfume_count(),
            "recommendable": c.execute("SELECT COUNT(*) FROM perfume WHERE recommendable=1").fetchone()[0],
            "sessions": c.execute("SELECT COUNT(*) FROM session").fetchone()[0],
            "events": counts,
            "thumbs": {"up": thumbs["up"] or 0, "down": thumbs["down"] or 0},
            "review_queue": review,
            "low_rated_picks": low,
            "zero_result_requests": zero,
            "unknown_notes": unknown,
        }
