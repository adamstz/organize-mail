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

        # Messages table (includes vector embedding columns for RAG)
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
                embedding vector(384),
                embedding_model TEXT,
                embedded_at TIMESTAMP WITH TIME ZONE
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

        # Email chunks table for long emails (RAG support)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_chunks (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding vector(384),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(message_id, chunk_index)
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

        # Create GIN index on labels JSONB column for fast label queries
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_classifications_labels_gin
            ON classifications USING GIN (labels jsonb_path_ops)
            """
        )

        # Create index on classifications.priority for priority filtering
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_classifications_priority
            ON classifications(priority) WHERE priority IS NOT NULL
            """
        )

        # Create index on messages.latest_classification_id for faster joins
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_latest_classification
            ON messages(latest_classification_id) WHERE latest_classification_id IS NOT NULL
            """
        )

        # Create HNSW indexes for vector similarity search (RAG support)
        # HNSW = Hierarchical Navigable Small World (fast approximate nearest neighbor)
        # vector_cosine_ops = use cosine distance for similarity
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_embedding_hnsw
            ON messages USING hnsw (embedding vector_cosine_ops)
            WHERE embedding IS NOT NULL
            """
        )
        
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_chunks_embedding_hnsw
            ON email_chunks USING hnsw (embedding vector_cosine_ops)
            """
        )
        
        # Index for looking up chunks by message_id
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_chunks_message_id
            ON email_chunks(message_id)
            """
        )
        
        # Index for sorting chunks by position
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_chunks_chunk_index
            ON email_chunks(message_id, chunk_index)
            """
        )

        # Add foreign key constraint if not exists
        try:
            cur.execute(
                """
                ALTER TABLE messages
                ADD CONSTRAINT fk_messages_classification
                FOREIGN KEY(latest_classification_id) REFERENCES classifications(id)
                """
            )
            conn.commit()
        except psycopg2.errors.DuplicateObject:
            # Constraint already exists, this is fine
            conn.rollback()
        except Exception as e:
            # Log other errors but don't fail initialization
            import sys
            print(f"Warning: Could not add foreign key constraint: {e}", file=sys.stderr)
            conn.rollback()

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
             internal_date, payload, raw, headers, fetched_at, has_attachments)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            (id, message_id, labels, priority, summary, model, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                message_id = EXCLUDED.message_id,
                labels = EXCLUDED.labels,
                priority = EXCLUDED.priority,
                summary = EXCLUDED.summary,
                model = EXCLUDED.model,
                created_at = EXCLUDED.created_at
            """,
            (
                record.id,
                record.message_id,
                Json(record.labels) if record.labels is not None else None,
                record.priority,
                record.summary,
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
                    summary=r['summary'],
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

    def update_message_latest_classification(self, message_id: str, classification_id: str) -> None:
        """Update the latest_classification_id for a message."""
        conn = self.connect()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE messages
            SET latest_classification_id = %s
            WHERE id = %s
            """,
            (classification_id, message_id)
        )

        conn.commit()
        cur.close()
        conn.close()

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
            ORDER BY m.internal_date DESC
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

    def get_label_counts(self) -> dict:
        """Get all unique classification labels with their counts efficiently."""
        conn = self.connect()
        cur = conn.cursor()

        try:
            # Native JSONB query - fast with GIN index
            cur.execute(
                """
                SELECT
                    jsonb_array_elements_text(labels) as label,
                    COUNT(*) as count
                FROM classifications
                WHERE labels IS NOT NULL
                GROUP BY label
                ORDER BY count DESC
                """
            )
            rows = cur.fetchall()
            result = {row[0]: row[1] for row in rows}
            cur.close()
            conn.close()
            return result
        except Exception:
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
            for (labels,) in rows:
                try:
                    # labels is now jsonb, psycopg2 auto-converts to list
                    if isinstance(labels, list):
                        for label in labels:
                            label_counts[label] = label_counts.get(label, 0) + 1
                except Exception:
                    pass
            return label_counts

    def list_messages_by_label(self, label: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by classification label (database-level filtering).

        Returns a tuple of (messages, total_count).
        Uses GIN index on classifications.labels for fast filtering.
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Use JSONB containment operator @> with GIN index on classifications table
        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE c.labels @> %s::jsonb
            ORDER BY m.internal_date DESC
            LIMIT %s OFFSET %s
            """,
            (json.dumps([label]), limit, offset)
        )
        rows = cur.fetchall()

        # Get total count for this label
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE c.labels @> %s::jsonb
            """,
            (json.dumps([label]),)
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
        return messages, total

    def list_messages_by_priority(self, priority: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by priority (database-level filtering).

        Returns a tuple of (messages, total_count).
        Uses index on classifications.priority for fast filtering.
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE LOWER(c.priority) = LOWER(%s)
            ORDER BY m.internal_date DESC
            LIMIT %s OFFSET %s
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
            WHERE LOWER(c.priority) = LOWER(%s)
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
        return messages, total

    def list_classified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only classified messages (database-level filtering).

        Returns a tuple of (messages, total_count).
        A message is classified if it has a latest_classification_id.
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            INNER JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.latest_classification_id IS NOT NULL
            ORDER BY m.internal_date DESC
            LIMIT %s OFFSET %s
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
        return messages, total

    def list_unclassified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only unclassified messages (database-level filtering).

        Returns a tuple of (messages, total_count).
        A message is unclassified if it has no latest_classification_id.
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            WHERE m.latest_classification_id IS NULL
            ORDER BY m.internal_date DESC
            LIMIT %s OFFSET %s
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
        total = cur.fetchone()["count"]

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
        return messages, total

    def similarity_search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        threshold: float = 0.0
    ) -> List[tuple[MailMessage, float]]:
        """Search for similar messages using vector similarity.
        
        Uses cosine distance with pgvector (<=> operator).
        Lower distance = more similar (0.0 = identical, 2.0 = opposite)
        
        Args:
            query_embedding: The embedding vector to search for
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0.0-1.0, where 1.0 is most similar)
        
        Returns:
            List of (message, similarity_score) tuples, ordered by similarity
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Convert similarity threshold to distance threshold
        # Cosine similarity = 1 - cosine distance
        # So if threshold is 0.7 similarity, distance must be <= 0.3
        distance_threshold = 1.0 - threshold
        
        # Search both messages table and chunks table, union the results
        query = """
            WITH email_scores AS (
                -- Search single embeddings
                SELECT 
                    m.id,
                    1 - (m.embedding <=> %s::vector) as similarity,
                    'single' as source
                FROM messages m
                WHERE m.embedding IS NOT NULL
                    AND (1 - (m.embedding <=> %s::vector)) >= %s
                
                UNION ALL
                
                -- Search chunked emails
                SELECT 
                    ec.message_id as id,
                    MAX(1 - (ec.embedding <=> %s::vector)) as similarity,
                    'chunks' as source
                FROM email_chunks ec
                WHERE (1 - (ec.embedding <=> %s::vector)) >= %s
                GROUP BY ec.message_id
            )
            SELECT DISTINCT ON (es.id)
                m.*, 
                c.labels as class_labels, 
                c.priority as class_priority, 
                c.summary as class_summary,
                es.similarity
            FROM email_scores es
            JOIN messages m ON m.id = es.id
            LEFT JOIN classifications c ON m.latest_classification_id = c.id
            ORDER BY es.id, es.similarity DESC
            LIMIT %s
        """
        
        # Execute with same embedding for all placeholders
        cur.execute(
            query,
            (
                query_embedding, query_embedding, threshold,  # single embeddings
                query_embedding, query_embedding, threshold,  # chunks
                limit
            )
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        results = []
        for r in rows:
            message = MailMessage(
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
            similarity = float(r['similarity'])
            results.append((message, similarity))
        
        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def list_messages_by_filters(
        self,
        priority: Optional[str] = None,
        labels: Optional[List[str]] = None,
        classified: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[MailMessage], int]:
        """List messages with combined filters (database-level filtering).

        Args:
            priority: Filter by priority (e.g., "high", "medium", "low")
            labels: Filter by labels - message must have ALL specified labels
            classified: If True, only classified messages. If False, only unclassified. If None, all.
            limit: Max messages to return
            offset: Skip this many results

        Returns a tuple of (messages, total_count).
        Uses GIN index on classifications.labels and B-tree index on priority for fast filtering.
        """
        conn = self.connect()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Build WHERE clauses dynamically
        where_clauses = []
        params = []

        # Classification filter
        if classified is True:
            where_clauses.append("m.latest_classification_id IS NOT NULL")
        elif classified is False:
            where_clauses.append("m.latest_classification_id IS NULL")

        # Priority filter
        if priority:
            where_clauses.append("LOWER(c.priority) = LOWER(%s)")
            params.append(priority)

        # Labels filter - must have ALL specified labels (AND logic)
        if labels:
            for label in labels:
                # Use JSONB containment operator @> for GIN index
                where_clauses.append("c.labels @> %s::jsonb")
                params.append(json.dumps([label]))

        # Determine JOIN type
        if classified is False or (classified is None and not priority and not labels):
            # LEFT JOIN for unclassified or when no classification filters
            join_type = "LEFT JOIN"
        else:
            # INNER JOIN when we need classification data
            join_type = "INNER JOIN"

        # Build WHERE clause
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Query with pagination
        query = f"""
            SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
            FROM messages m
            {join_type} classifications c ON m.latest_classification_id = c.id
            WHERE {where_sql}
            ORDER BY m.internal_date DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        cur.execute(query, params)
        rows = cur.fetchall()

        # Get total count with same filters
        count_query = f"""
            SELECT COUNT(*) as count
            FROM messages m
            {join_type} classifications c ON m.latest_classification_id = c.id
            WHERE {where_sql}
        """
        cur.execute(count_query, params[:-2])  # Exclude limit/offset
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
        return messages, total
