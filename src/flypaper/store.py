"""SQLite store for FlyPaper items, events, and specialists."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

CATEGORIES = ("Prompt", "CLI", "Snippet", "Secret", "URL", "File", "Noise")

DEFAULT_DB = Path(os.environ.get("FLYPAPER_DB", Path.home() / ".flypaper" / "flypaper.db"))


def _now() -> float:
    return time.time()


class Store:
    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL DEFAULT 'text',
                category TEXT NOT NULL,
                subcategory TEXT,
                body TEXT NOT NULL,
                body_redacted TEXT,
                path TEXT,
                filename TEXT,
                description TEXT,
                fingerprint TEXT,
                last4 TEXT,
                secret_status TEXT,
                trigger TEXT UNIQUE,
                pin INTEGER NOT NULL DEFAULT 0,
                meta TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_used_at REAL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                kind TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS specialists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subcategory TEXT NOT NULL,
                parent TEXT NOT NULL,
                policy TEXT NOT NULL DEFAULT '{}',
                trigger_prefix TEXT,
                item_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                UNIQUE(parent, subcategory)
            );
            CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
            CREATE INDEX IF NOT EXISTS idx_items_trigger ON items(trigger);
            CREATE INDEX IF NOT EXISTS idx_events_item ON events(item_id);
            """
        )
        self._conn.commit()

    def add_event(self, kind: str, item_id: Optional[int] = None) -> None:
        self._conn.execute(
            "INSERT INTO events (item_id, kind, created_at) VALUES (?, ?, ?)",
            (item_id, kind, _now()),
        )
        self._conn.commit()

    def insert_item(
        self,
        *,
        category: str,
        body: str,
        kind: str = "text",
        subcategory: Optional[str] = None,
        body_redacted: Optional[str] = None,
        path: Optional[str] = None,
        filename: Optional[str] = None,
        description: Optional[str] = None,
        fingerprint: Optional[str] = None,
        last4: Optional[str] = None,
        secret_status: Optional[str] = None,
        trigger: Optional[str] = None,
        pin: int = 0,
        meta: Optional[dict] = None,
    ) -> dict:
        now = _now()
        cur = self._conn.execute(
            """
            INSERT INTO items (
                kind, category, subcategory, body, body_redacted, path, filename,
                description, fingerprint, last4, secret_status, trigger, pin, meta,
                created_at, updated_at, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kind,
                category,
                subcategory,
                body,
                body_redacted,
                path,
                filename,
                description,
                fingerprint,
                last4,
                secret_status,
                trigger,
                pin,
                json.dumps(meta or {}),
                now,
                now,
                now,
            ),
        )
        self._conn.commit()
        item_id = int(cur.lastrowid)
        self.add_event("file", item_id)
        self._maybe_spawn_specialist(category, subcategory)
        return self.get_item(item_id)

    def get_item(self, item_id: int) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_items(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM items ORDER BY updated_at DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def find_by_trigger(self, trigger: str) -> Optional[dict]:
        t = trigger if trigger.startswith(";") else f";{trigger}"
        row = self._conn.execute("SELECT * FROM items WHERE trigger = ?", (t,)).fetchone()
        return self._row_to_dict(row) if row else None

    def find_near_matches(self, text: str, limit: int = 5) -> list[dict]:
        """Near-dup: same trigger prefix or high body prefix overlap."""
        text = (text or "").strip()
        if not text:
            return []
        rows = self._conn.execute("SELECT * FROM items").fetchall()
        scored: list[tuple[float, dict]] = []
        for row in rows:
            item = self._row_to_dict(row)
            body = item.get("body") or ""
            if not body:
                continue
            if body == text:
                scored.append((1.0, item))
                continue
            # prefix / containment similarity
            shorter, longer = (body, text) if len(body) < len(text) else (text, body)
            if shorter and shorter in longer:
                ratio = len(shorter) / max(len(longer), 1)
                if ratio >= 0.7:
                    scored.append((ratio, item))
                    continue
            # first 80 chars overlap
            a, b = body[:80], text[:80]
            common = sum(1 for x, y in zip(a, b) if x == y)
            if len(a) and common / max(len(a), len(b), 1) >= 0.85:
                scored.append((common / max(len(a), len(b), 1), item))
        scored.sort(key=lambda x: -x[0])
        return [it for _, it in scored[:limit]]

    def update_body(self, item_id: int, text: str, body_redacted: Optional[str] = None) -> Optional[dict]:
        now = _now()
        self._conn.execute(
            """
            UPDATE items SET body = ?, body_redacted = COALESCE(?, body_redacted),
                updated_at = ?, last_used_at = ? WHERE id = ?
            """,
            (text, body_redacted, now, now, item_id),
        )
        self._conn.commit()
        self.add_event("update", item_id)
        return self.get_item(item_id)

    def pin_item(self, item_id: int, pinned: bool = True) -> Optional[dict]:
        self._conn.execute(
            "UPDATE items SET pin = ?, updated_at = ? WHERE id = ?",
            (1 if pinned else 0, _now(), item_id),
        )
        self._conn.commit()
        return self.get_item(item_id)

    def delete_item(self, item_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self._conn.commit()
        self.add_event("dismiss", item_id)
        return cur.rowcount > 0

    def touch_retrieve(self, item_id: int) -> None:
        self._conn.execute(
            "UPDATE items SET last_used_at = ? WHERE id = ?",
            (_now(), item_id),
        )
        self._conn.commit()
        self.add_event("retrieve", item_id)

    def event_counts(self) -> dict[int, dict[str, Any]]:
        """Per-item frequency and last retrieve time."""
        rows = self._conn.execute(
            """
            SELECT item_id,
                   SUM(CASE WHEN kind IN ('file','retrieve','update') THEN 1 ELSE 0 END) AS freq,
                   MAX(CASE WHEN kind = 'retrieve' THEN created_at ELSE NULL END) AS last_retrieve,
                   MAX(created_at) AS last_event
            FROM events
            WHERE item_id IS NOT NULL
            GROUP BY item_id
            """
        ).fetchall()
        out: dict[int, dict[str, Any]] = {}
        for r in rows:
            out[int(r["item_id"])] = {
                "freq": int(r["freq"] or 0),
                "last_retrieve": r["last_retrieve"],
                "last_event": r["last_event"],
            }
        return out

    def list_specialists(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM specialists ORDER BY item_count DESC, created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def subcategories(self, prefix: str = "", category: Optional[str] = None) -> list[str]:
        q = "SELECT DISTINCT subcategory FROM items WHERE subcategory IS NOT NULL AND subcategory != ''"
        params: list[Any] = []
        if category:
            q += " AND category = ?"
            params.append(category)
        if prefix:
            q += " AND subcategory LIKE ?"
            params.append(f"{prefix}%")
        q += " ORDER BY subcategory"
        return [r[0] for r in self._conn.execute(q, params).fetchall()]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])

    def _maybe_spawn_specialist(self, category: str, subcategory: Optional[str]) -> None:
        if not subcategory:
            return
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM items WHERE category = ? AND subcategory = ?",
            (category, subcategory),
        ).fetchone()
        count = int(row["c"])
        if count < 5:
            return
        existing = self._conn.execute(
            "SELECT id FROM specialists WHERE parent = ? AND subcategory = ?",
            (category, subcategory),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE specialists SET item_count = ? WHERE id = ?",
                (count, existing["id"]),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO specialists (subcategory, parent, policy, trigger_prefix, item_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    subcategory,
                    category,
                    json.dumps({"rule": "auto", "min_items": 5}),
                    f";{subcategory.lower().replace(' ', '-')[:12]}",
                    count,
                    _now(),
                ),
            )
        self._conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["meta"] = json.loads(d.get("meta") or "{}")
        except json.JSONDecodeError:
            d["meta"] = {}
        return d
