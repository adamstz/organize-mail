from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from ..models.message import MailMessage
from .storage_interface import StorageBackend


def get_db_url() -> str:
    """Get PostgreSQL connection URL from environment variables.
    
    Raises ValueError if DATABASE_URL is not set.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "DATABASE_URL environment variable is required for PostgreSQL storage. "
            "Set it to a connection string like: postgresql://user:password@host:port/database"
        )
    return db_url


class PostgresStorage(StorageBackend):
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or get_db_url()

    def connect(self):
        """Create a connection to PostgreSQL."""
        conn = psycopg2.connect(self.db_url)
        return conn

    def init_db(self) -> None:
        """Initialize database tables and indexes."""
        conn = self.connect()
        cur = conn.cursor()
        
        # Messages table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                from_addr TEXT,
                to_addr TEXT,
                subject TEXT,
                snippet TEXT,
                labels JSONB,
                internal_date BIGINT,
                payload JSONB,
                raw TEXT,
                headers JSONB,
                fetched_at TIMESTAMP WITH TIME ZONE,
                has_attachments BOOLEAN DEFAULT FALSE,
                latest_classification_id TEXT,
                classification_labels JSONB,
                priority TEXT,
                summary TEXT
            )
            """
        )
        
        # Metadata table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        
        # Classifications table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS classifications (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                labels JSONB,
                priority TEXT,
                summary TEXT,
                model TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id)
            )
            """
        )
        
        # Create indexes for faster lookups
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
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_fetched_at 
            ON messages(fetched_at DESC)
            """
        )
        
        # Add foreign key constraint if not exists (PostgreSQL handles this gracefully)
        try:
            cur.execute(
                """
                ALTER TABLE messages 
                ADD CONSTRAINT fk_messages_classification 
                FOREIGN KEY(latest_classification_id) REFERENCES classifications(id)
                """
            )
        except psycopg2.errors.DuplicateObject:
            conn.rollback()
        else:
            conn.commit()
        
        conn.commit()
        cur.close()
        conn.close()

    def save_message(self, msg: MailMessage) -> None:
        """Save or update a message in the database."""
        conn = self.connect()
        cur = conn.cursor()
        
        cur.execute(
            """
            INSERT INTO messages
            (id, thread_id, from_addr, to_addr, subject, snippet, labels, 
             internal_date, payload, raw, headers, fetched_at, classification_labels, 
             priority, summary, has_attachments)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                thread_id = EXCLUDED.thread_id,
                from_addr = EXCLUDED.from_addr,
                to_addr = EXCLUDED.to_addr,
                subject = EXCLUDED.subject,
                snippet = EXCLUDED.snippet,
                labels = EXCLUDED.labels,
                internal_date = EXCLUDED.internal_date,
                payload = EXCLUDED.payload,
                raw = EXCLUDED.raw,
                headers = EXCLUDED.headers,
                fetched_at = EXCLUDED.fetched_at,
                classification_labels = EXCLUDED.classification_labels,
                priority = EXCLUDED.priority,
                summary = EXCLUDED.summary,
                has_attachments = EXCLUDED.has_attachments
            """,
            (
                msg.id,
                msg.thread_id,
                msg.from_,
                msg.to,
                msg.subject,
                msg.snippet,
                Json(msg.labels) if msg.labels is not None else None,
                msg.internal_date,
                Json(msg.payload) if msg.payload is not None else None,
                msg.raw,
                Json(msg.headers) if msg.headers is not None else None,
                datetime.now(timezone.utc),
                Json(msg.classification_labels) if msg.classification_labels is not None else None,
                msg.priority,
                msg.summary,
                msg.has_attachments,
            ),
        )
        
        conn.commit()
        cur.close()
        conn.close()

    def save_classification_record(self, record) -> None:
        """Persist a ClassificationRecord-like object."""
        conn = self.connect()
        cur = conn.cursor()
        
        cur.execute(
            """
            INSERT INTO classifications
            (id, message_id, labels, priority, model, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                message_id = EXCLUDED.message_id,
                labels = EXCLUDED.labels,
                priority = EXCLUDED.priority,
                model = EXCLUDED.model,
                created_at = EXCLUDED.created_at
            """,
            (
                record.id,
                record.message_id,
                Json(record.labels) if record.labels is not None else None,
                record.priority,
                record.model,
                record.created_at if record.created_at is not None else None,
            ),
        )
        
        conn.commit()
        cur.close()
        conn.close()

    def list_classification_records_for_message(self, message_id: str):
        """Get all classification records for a message, ordered by creation date."""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            "SELECT * FROM classifications WHERE message_id = %s ORDER BY created_at DESC",
            (message_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        out = []
        from ..models.classification_record import ClassificationRecord

        for r in rows:
            # JSONB columns are automatically deserialized by psycopg2
            labels = r['labels'] if r['labels'] is not None else []
            created_at = r['created_at']
            
            out.append(
                ClassificationRecord(
                    id=r['id'],
                    message_id=r['message_id'],
                    labels=labels,
                    priority=r['priority'],
                    model=r['model'],
                    created_at=created_at,
                )
            )
        return out

    def create_classification(self, message_id: str, labels: List[str], priority: str, summary: str, model: str = None) -> str:
        """Create a new classification record and link it to the message.
        
        Returns the classification ID.
        """
        import uuid
        
        classification_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        
        conn = self.connect()
        cur = conn.cursor()
        
        # Insert classification record
        cur.execute(
            """
            INSERT INTO classifications
            (id, message_id, labels, priority, summary, model, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                classification_id,
                message_id,
                Json(labels) if labels else None,
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
            SET latest_classification_id = %s
            WHERE id = %s
            """,
            (classification_id, message_id),
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return classification_id
    
    def get_latest_classification(self, message_id: str) -> Optional[dict]:
        """Get the most recent classification for a message.
        
        Returns dict with: id, labels, priority, summary, model, created_at
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            """
            SELECT c.id, c.labels, c.priority, c.summary, c.model, c.created_at
            FROM classifications c
            INNER JOIN messages m ON m.latest_classification_id = c.id
            WHERE m.id = %s
            """,
            (message_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            return None
        
        return {
            "id": row['id'],
            "labels": row['labels'] if row['labels'] else [],
            "priority": row['priority'],
            "summary": row['summary'],
            "model": row['model'],
            "created_at": row['created_at'].isoformat() if row['created_at'] else None,
        }

    def get_message_ids(self) -> List[str]:
        """Get all message IDs."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM messages")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0] for r in rows]
    
    def get_message_by_id(self, message_id: str) -> Optional[MailMessage]:
        """Get a single message by ID with latest classification."""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.id = %s
            """,
            (message_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            return None
        
        return MailMessage(
            id=row['id'],
            thread_id=row['thread_id'],
            from_=row['from_addr'],
            to=row['to_addr'],
            subject=row['subject'],
            snippet=row['snippet'],
            labels=row['labels'],
            internal_date=row['internal_date'],
            payload=row['payload'],
            raw=row['raw'],
            headers=row['headers'] or {},
            classification_labels=row['class_labels'],
            priority=row['class_priority'],
            summary=row['class_summary'],
            has_attachments=row['has_attachments'] or False,
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
        cur.close()
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
        cur.close()
        conn.close()
        return count

    def list_messages(self, limit: int = 100, offset: int = 0) -> List[MailMessage]:
        """List messages with their latest classifications."""
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            ORDER BY m.fetched_at DESC 
            LIMIT %s OFFSET %s
            """,
            (limit, offset)
        )
        rows = cur.fetchall()
        cur.close()
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
                    labels=r['labels'],
                    internal_date=r['internal_date'],
                    payload=r['payload'],
                    raw=r['raw'],
                    headers=r['headers'] or {},
                    classification_labels=r['class_labels'],
                    priority=r['class_priority'],
                    summary=r['class_summary'],
                    has_attachments=r['has_attachments'] or False,
                )
            )
        return out

    def get_history_id(self) -> Optional[str]:
        """Get the stored Gmail history ID."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT value FROM metadata WHERE key = %s", ("historyId",))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0]
        return None

    def set_history_id(self, history_id: str) -> None:
        """Store the Gmail history ID."""
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO metadata (key, value) 
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            ("historyId", history_id)
        )
        conn.commit()
        cur.close()
        conn.close()
