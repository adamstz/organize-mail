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
                has_attachments INTEGER,
                latest_classification_id TEXT,
                FOREIGN KEY(latest_classification_id) REFERENCES classifications(id)
            )
            """
        )
        
        # Migration: Add latest_classification_id column to existing tables
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN latest_classification_id TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Migration: Add has_attachments if it doesn't exist
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN has_attachments INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Keep old classification columns for backward compatibility during migration
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN classification_labels TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN priority TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN summary TEXT")
        except sqlite3.OperationalError:
            pass
        
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        
        # Classifications table - now the primary source of truth
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS classifications (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                labels TEXT,
                priority TEXT,
                summary TEXT,
                model TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id)
            )
            """
        )
        
        # Create index for faster lookups
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_classifications_message_id 
            ON classifications(message_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_classifications_created_at 
            ON classifications(created_at DESC)
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
            (id, thread_id, from_addr, to_addr, subject, snippet, labels, internal_date, payload, raw, headers, fetched_at, classification_labels, priority, summary, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                1 if msg.has_attachments else 0,
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
            (id, message_id, labels, priority, summary, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.message_id,
                self._serialize(record.labels) if record.labels is not None else None,
                record.priority,
                record.summary,
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
            created_at = r[6]
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
                    summary=r[4],
                    model=r[5],
                    created_at=created_dt,
                )
            )
        return out

    def create_classification(self, message_id: str, labels: List[str], priority: str, summary: str, model: str = None) -> str:
        """Create a new classification record and link it to the message.
        
        Returns the classification ID.
        """
        import uuid
        from datetime import datetime, timezone
        
        classification_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        conn = self.connect()
        cur = conn.cursor()
        
        # Insert classification record
        cur.execute(
            """
            INSERT INTO classifications
            (id, message_id, labels, priority, summary, model, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                classification_id,
                message_id,
                self._serialize(labels) if labels else None,
                priority,
                summary,
                model,
                created_at,
            ),
        )
        
        # Update message to point to this latest classification
        cur.execute(
            """
            UPDATE messages
            SET latest_classification_id = ?
            WHERE id = ?
            """,
            (classification_id, message_id),
        )
        
        conn.commit()
        conn.close()
        
        return classification_id
    
    def get_latest_classification(self, message_id: str) -> Optional[dict]:
        """Get the most recent classification for a message.
        
        Returns dict with: id, labels, priority, summary, model, created_at
        """
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.labels, c.priority, c.summary, c.model, c.created_at
            FROM classifications c
            INNER JOIN messages m ON m.latest_classification_id = c.id
            WHERE m.id = ?
            """,
            (message_id,),
        )
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "labels": self._deserialize(row[1]) if row[1] else [],
            "priority": row[2],
            "summary": row[3],
            "model": row[4],
            "created_at": row[5],
        }

    def get_message_ids(self) -> List[str]:
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM messages")
        rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]
    
    def get_message_by_id(self, message_id: str) -> Optional[MailMessage]:
        """Get a single message by ID with latest classification."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.id = ?
            """,
            (message_id,)
        )
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Parse row data - classification from JOIN comes last
        labels = self._deserialize(row[6])
        payload = self._deserialize(row[8])
        headers = self._deserialize(row[10]) or {}
        has_attachments = bool(row[11]) if len(row) > 11 and row[11] is not None else False
        
        # Classification data from the JOIN (last 3 columns)
        classification_labels = self._deserialize(row[-3]) if row[-3] else None
        priority = row[-2]
        summary = row[-1]
        
        return MailMessage(
            id=row[0],
            thread_id=row[1],
            from_=row[2],
            to=row[3],
            subject=row[4],
            snippet=row[5],
            labels=labels,
            internal_date=row[7],
            payload=payload,
            raw=row[9],
            headers=headers,
            classification_labels=classification_labels,
            priority=priority,
            summary=summary,
            has_attachments=has_attachments,
        )
    
    def get_unclassified_message_ids(self) -> List[str]:
        """Get IDs of messages that haven't been classified yet."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM messages 
            WHERE latest_classification_id IS NULL
        """)
        rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]
    
    def count_classified_messages(self) -> int:
        """Count how many messages have been classified."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM messages 
            WHERE latest_classification_id IS NOT NULL
        """)
        count = cur.fetchone()[0]
        conn.close()
        return count

    def list_messages(self, limit: int = 100, offset: int = 0) -> List[MailMessage]:
        """List messages with their latest classifications."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            ORDER BY m.fetched_at DESC 
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        rows = cur.fetchall()
        conn.close()
        out: List[MailMessage] = []
        for r in rows:
            labels = self._deserialize(r[6])
            payload = self._deserialize(r[8])
            headers = self._deserialize(r[10]) or {}
            has_attachments = bool(r[11]) if len(r) > 11 and r[11] is not None else False
            
            # Classification data from the JOIN (last 3 columns)
            classification_labels = self._deserialize(r[-3]) if r[-3] else None
            priority = r[-2]
            summary = r[-1]
            
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
                    has_attachments=has_attachments,
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
