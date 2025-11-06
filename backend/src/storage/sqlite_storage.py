from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from ..models.message import MailMessage
from .storage_interface import StorageBackend


def default_db_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".organize_mail.db")


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or default_db_path()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                from_addr TEXT,
                to_addr TEXT,
                subject TEXT,
                snippet TEXT,
                labels TEXT,
                internal_date INTEGER,
                payload TEXT,
                raw TEXT,
                headers TEXT,
                fetched_at TEXT,
                classification_labels TEXT,
                priority TEXT,
                summary TEXT
            )
            """
        )
        
        # Add classification columns to existing tables (migration)
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN classification_labels TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN priority TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN summary TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # Persisted classification records
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS classifications (
                id TEXT PRIMARY KEY,
                message_id TEXT,
                labels TEXT,
                priority TEXT,
                model TEXT,
                created_at TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def _serialize(self, obj) -> str:
        return json.dumps(obj, ensure_ascii=False)

    def _deserialize(self, text: Optional[str]):
        if not text:
            return None
        return json.loads(text)

    def save_message(self, msg: MailMessage) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO messages
            (id, thread_id, from_addr, to_addr, subject, snippet, labels, internal_date, payload, raw, headers, fetched_at, classification_labels, priority, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg.id,
                msg.thread_id,
                msg.from_,
                msg.to,
                msg.subject,
                msg.snippet,
                self._serialize(msg.labels) if msg.labels is not None else None,
                msg.internal_date,
                self._serialize(msg.payload) if msg.payload is not None else None,
                msg.raw,
                self._serialize(msg.headers) if msg.headers is not None else None,
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                self._serialize(msg.classification_labels) if msg.classification_labels is not None else None,
                msg.priority,
                msg.summary,
            ),
        )
        conn.commit()
        conn.close()

    def save_classification_record(self, record) -> None:
        """Persist a ClassificationRecord-like object."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO classifications
            (id, message_id, labels, priority, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.message_id,
                self._serialize(record.labels) if record.labels is not None else None,
                record.priority,
                record.model,
                record.created_at.isoformat() if record.created_at is not None else None,
            ),
        )
        conn.commit()
        conn.close()

    def list_classification_records_for_message(self, message_id: str):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM classifications WHERE message_id = ? ORDER BY created_at DESC", (message_id,))
        rows = cur.fetchall()
        conn.close()

        out = []
        from ..models.classification_record import ClassificationRecord
        from datetime import datetime

        for r in rows:
            labels = self._deserialize(r[2]) or []
            created_at = r[5]
            created_dt = None
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at)
                except Exception:
                    created_dt = None
            out.append(
                ClassificationRecord(
                    id=r[0],
                    message_id=r[1],
                    labels=labels,
                    priority=r[3],
                    model=r[4],
                    created_at=created_dt,
                )
            )
        return out

    def get_message_ids(self) -> List[str]:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM messages")
        rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def list_messages(self, limit: int = 100) -> List[MailMessage]:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM messages ORDER BY fetched_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        out: List[MailMessage] = []
        for r in rows:
            labels = self._deserialize(r[6])
            payload = self._deserialize(r[8])
            headers = self._deserialize(r[10]) or {}
            classification_labels = self._deserialize(r[12]) if len(r) > 12 else None
            priority = r[13] if len(r) > 13 else None
            summary = r[14] if len(r) > 14 else None
            out.append(
                MailMessage(
                    id=r[0],
                    thread_id=r[1],
                    from_=r[2],
                    to=r[3],
                    subject=r[4],
                    snippet=r[5],
                    labels=labels,
                    internal_date=r[7],
                    payload=payload,
                    raw=r[9],
                    headers=headers,
                    classification_labels=classification_labels,
                    priority=priority,
                    summary=summary,
                )
            )
        return out

    def get_history_id(self) -> Optional[str]:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT value FROM metadata WHERE key = ?", ("historyId",))
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
        return None

    def set_history_id(self, history_id: str) -> None:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("historyId", history_id))
        conn.commit()
        conn.close()
