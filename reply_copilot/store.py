"""Local state in one SQLite file: seen message ids, pipeline outcomes, and the approval queue.

The file lives under data/ (gitignored). Raw message text is stored only here.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
  channel TEXT NOT NULL, message_id TEXT NOT NULL, first_seen TEXT NOT NULL,
  PRIMARY KEY (channel, message_id)
);
CREATE TABLE IF NOT EXISTS outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL, message_id TEXT NOT NULL,
  created TEXT NOT NULL, outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL, message_id TEXT NOT NULL,
  sender TEXT, original TEXT, reply TEXT NOT NULL, link TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | dismissed
  created TEXT NOT NULL, updated TEXT NOT NULL,
  UNIQUE (channel, message_id)
);
"""
STATUSES = ("pending", "done", "dismissed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def is_seen(self, channel: str, message_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE channel=? AND message_id=?",
                               (channel, message_id)).fetchone() is not None

    def mark_seen(self, channel: str, message_id: str) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO seen VALUES (?,?,?)", (channel, message_id, _now()))

    def save_outcome(self, channel: str, outcome: dict) -> None:
        with self.db:
            self.db.execute("INSERT INTO outcomes (channel, message_id, created, outcome) VALUES (?,?,?,?)",
                            (channel, outcome["message_id"], _now(), json.dumps(outcome, ensure_ascii=False)))

    def enqueue(self, channel: str, message_id: str, reply: str, *, sender: str = "",
                original: str = "", link: str = "") -> int:
        """Queue a reply for the owner's approval. Re-queuing the same message replaces the text."""
        with self.db:
            self.db.execute(
                "INSERT INTO queue (channel, message_id, sender, original, reply, link, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(channel, message_id) DO UPDATE SET "
                "reply=excluded.reply, updated=excluded.updated, status='pending'",
                (channel, message_id, sender, original, reply, link, _now(), _now()))
        row = self.db.execute("SELECT id FROM queue WHERE channel=? AND message_id=?",
                              (channel, message_id)).fetchone()
        return int(row["id"])

    def pending(self, channel: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM queue WHERE status='pending'", []
        if channel:
            sql, args = sql + " AND channel=?", [channel]
        return [dict(r) for r in self.db.execute(sql + " ORDER BY id", args)]

    def set_status(self, queue_id: int, status: str) -> bool:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        with self.db:
            cur = self.db.execute("UPDATE queue SET status=?, updated=? WHERE id=?", (status, _now(), queue_id))
        return cur.rowcount == 1
