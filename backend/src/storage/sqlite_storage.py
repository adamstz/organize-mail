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
            (id, thread_id, from_addr, to_addr, subject, snippet, labels, internal_date,
             payload, raw, headers, fetched_at, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            SELECT m.id, m.thread_id, m.from_addr, m.to_addr, m.subject, m.snippet,
                   m.labels, m.internal_date, m.payload, m.raw, m.headers, m.has_attachments,
                   c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
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

        # Use row_factory=Row to access by column name
        return MailMessage(
            id=row['id'],
            thread_id=row['thread_id'],
            from_=row['from_addr'],
            to=row['to_addr'],
            subject=row['subject'],
            snippet=row['snippet'],
            labels=self._deserialize(row['labels']),
            internal_date=row['internal_date'],
            payload=self._deserialize(row['payload']),
            raw=row['raw'],
            headers=self._deserialize(row['headers']) or {},
            has_attachments=bool(row['has_attachments']) if row['has_attachments'] is not None else False,
            classification_labels=self._deserialize(row['class_labels']) if row['class_labels'] else None,
            priority=row['class_priority'],
            summary=row['class_summary'],
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
            SELECT m.id, m.thread_id, m.from_addr, m.to_addr, m.subject, m.snippet,
                   m.labels, m.internal_date, m.payload, m.raw, m.headers, m.has_attachments,
                   c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            ORDER BY m.internal_date DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        rows = cur.fetchall()
        conn.close()
        out: List[MailMessage] = []
        for r in rows:
            out.append(
                MailMessage(
                    id=r['id'],
                    thread_id=r['thread_id'],
                    from_=r['from_addr'],
                    to=r['to_addr'],
                    subject=r['subject'],
                    snippet=r['snippet'],
                    labels=self._deserialize(r['labels']),
                    internal_date=r['internal_date'],
                    payload=self._deserialize(r['payload']),
                    raw=r['raw'],
                    headers=self._deserialize(r['headers']) or {},
                    has_attachments=bool(r['has_attachments']) if r['has_attachments'] is not None else False,
                    classification_labels=self._deserialize(r['class_labels']) if r['class_labels'] else None,
                    priority=r['class_priority'],
                    summary=r['class_summary'],
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

    def get_label_counts(self) -> dict:
        """Get all unique classification labels with their counts efficiently."""
        conn = self.connect()
        cur = conn.cursor()

        try:
            # Use json_each to efficiently extract and count labels
            cur.execute(
                """
                SELECT json_each.value as label, COUNT(*) as count
                FROM classifications, json_each(classifications.labels)
                WHERE classifications.labels IS NOT NULL
                GROUP BY label
                ORDER BY count DESC
                """
            )
            rows = cur.fetchall()
            result = {row[0]: row[1] for row in rows}
            cur.close()
            conn.close()
            return result
        except sqlite3.OperationalError:
            # Fallback: fetch labels column only and count in Python
            try:
                cur.close()
                conn.close()
            except Exception:
                pass

            conn = self.connect()
            cur = conn.cursor()
            cur.execute("SELECT labels FROM classifications WHERE labels IS NOT NULL")
            rows = cur.fetchall()
            cur.close()
            conn.close()

            label_counts = {}
            for (labels_str,) in rows:
                try:
                    labels = self._deserialize(labels_str)
                    if isinstance(labels, list):
                        for label in labels:
                            label_counts[label] = label_counts.get(label, 0) + 1
                except Exception:
                    pass
            return label_counts

    def list_messages_by_label(self, label: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by classification label.

        Returns a tuple of (messages, total_count).
        """
        conn = self.connect()
        cur = conn.cursor()

        # Get messages with the specified label
        cur.execute(
            """
            SELECT m.id, m.thread_id, m.from_addr, m.to_addr, m.subject, m.snippet,
                   m.labels, m.internal_date, m.payload, m.raw, m.headers, m.has_attachments,
                   c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE c.labels LIKE ?
            ORDER BY m.internal_date DESC
            LIMIT ? OFFSET ?
            """,
            (f'%"{label}"%', limit, offset)
        )
        rows = cur.fetchall()

        # Get total count for this label
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE c.labels LIKE ?
            """,
            (f'%"{label}"%',)
        )
        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        messages = []
        for r in rows:
            classification_labels = self._deserialize(r['class_labels']) if r['class_labels'] else None

            # Filter in Python to ensure exact label match
            if classification_labels and label in classification_labels:
                messages.append(
                    MailMessage(
                        id=r['id'],
                        thread_id=r['thread_id'],
                        from_=r['from_addr'],
                        to=r['to_addr'],
                        subject=r['subject'],
                        snippet=r['snippet'],
                        labels=self._deserialize(r['labels']),
                        internal_date=r['internal_date'],
                        payload=self._deserialize(r['payload']),
                        raw=r['raw'],
                        headers=self._deserialize(r['headers']) or {},
                        has_attachments=bool(r['has_attachments']) if r['has_attachments'] is not None else False,
                        classification_labels=classification_labels,
                        priority=r['class_priority'],
                        summary=r['class_summary'],
                    )
                )

        return messages, total

    def list_messages_by_priority(self, priority: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by priority.

        Returns a tuple of (messages, total_count).
        """
        conn = self.connect()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT m.id, m.thread_id, m.from_addr, m.to_addr, m.subject, m.snippet,
                   m.labels, m.internal_date, m.payload, m.raw, m.headers, m.has_attachments,
                   c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE LOWER(c.priority) = LOWER(?)
            ORDER BY m.internal_date DESC
            LIMIT ? OFFSET ?
            """,
            (priority, limit, offset)
        )
        rows = cur.fetchall()

        # Get total count for this priority
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE LOWER(c.priority) = LOWER(?)
            """,
            (priority,)
        )
        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        messages = []
        for r in rows:
            messages.append(
                MailMessage(
                    id=r['id'],
                    thread_id=r['thread_id'],
                    from_=r['from_addr'],
                    to=r['to_addr'],
                    subject=r['subject'],
                    snippet=r['snippet'],
                    labels=self._deserialize(r['labels']),
                    internal_date=r['internal_date'],
                    payload=self._deserialize(r['payload']),
                    raw=r['raw'],
                    headers=self._deserialize(r['headers']) or {},
                    has_attachments=bool(r['has_attachments']) if r['has_attachments'] is not None else False,
                    classification_labels=self._deserialize(r['class_labels']) if r['class_labels'] else None,
                    priority=r['class_priority'],
                    summary=r['class_summary'],
                )
            )

        return messages, total

    def list_classified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only classified messages.

        Returns a tuple of (messages, total_count).
        A message is classified if it has a latest_classification_id.
        """
        conn = self.connect()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT m.id, m.thread_id, m.from_addr, m.to_addr, m.subject, m.snippet,
                   m.labels, m.internal_date, m.payload, m.raw, m.headers, m.has_attachments,
                   c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.latest_classification_id IS NOT NULL
            ORDER BY m.internal_date DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        rows = cur.fetchall()

        # Get total count
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM messages
            WHERE latest_classification_id IS NOT NULL
            """
        )
        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        messages = []
        for r in rows:
            messages.append(
                MailMessage(
                    id=r['id'],
                    thread_id=r['thread_id'],
                    from_=r['from_addr'],
                    to=r['to_addr'],
                    subject=r['subject'],
                    snippet=r['snippet'],
                    labels=self._deserialize(r['labels']),
                    internal_date=r['internal_date'],
                    payload=self._deserialize(r['payload']),
                    raw=r['raw'],
                    headers=self._deserialize(r['headers']) or {},
                    has_attachments=bool(r['has_attachments']) if r['has_attachments'] is not None else False,
                    classification_labels=self._deserialize(r['class_labels']) if r['class_labels'] else None,
                    priority=r['class_priority'],
                    summary=r['class_summary'],
                )
            )

        return messages, total

    def list_unclassified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only unclassified messages.

        Returns a tuple of (messages, total_count).
        A message is unclassified if it has no latest_classification_id.
        """
        conn = self.connect()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT m.id, m.thread_id, m.from_addr, m.to_addr, m.subject, m.snippet,
                   m.labels, m.internal_date, m.payload, m.raw, m.headers, m.has_attachments,
                   c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.latest_classification_id IS NULL
            ORDER BY m.internal_date DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        rows = cur.fetchall()

        # Get total count
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM messages
            WHERE latest_classification_id IS NULL
            """
        )
        total = cur.fetchone()['count']

        cur.close()
        conn.close()

        messages = []
        for r in rows:
            messages.append(
                MailMessage(
                    id=r['id'],
                    thread_id=r['thread_id'],
                    from_=r['from_addr'],
                    to=r['to_addr'],
                    subject=r['subject'],
                    snippet=r['snippet'],
                    labels=self._deserialize(r['labels']),
                    internal_date=r['internal_date'],
                    payload=self._deserialize(r['payload']),
                    raw=r['raw'],
                    headers=self._deserialize(r['headers']) or {},
                    has_attachments=bool(r['has_attachments']) if r['has_attachments'] is not None else False,
                    classification_labels=self._deserialize(r['class_labels']) if r['class_labels'] else None,
                    priority=r['class_priority'],
                    summary=r['class_summary'],
                )
            )

        return messages, total
