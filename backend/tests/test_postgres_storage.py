"""Tests for PostgreSQL storage backend.

These tests exercise the PostgresStorage implementation of the StorageBackend
interface, including message storage, classification records, and metadata.
"""

import os
import json
import hashlib
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.models.message import MailMessage
from src.models.classification_record import ClassificationRecord
from src.storage.postgres_storage import PostgresStorage

# Helper to check if Postgres is available
def _is_postgres_available():
    """Check if test database is available."""
    try:
        import psycopg2
        db_url = _get_test_db_url()
        conn = psycopg2.connect(db_url)
        conn.close()
        return True
    except Exception:
        return False


def _get_test_db_url() -> str:
    """Get test database URL using the same logic as production storage.
    
    Returns connection string built from TEST_DATABASE_URL or individual env vars.
    """
    db_url = os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        # Build from individual components if TEST_DATABASE_URL not set
        # Use TEST_* variants first, fall back to POSTGRES_* vars (but always default to test_mail_db)
        user = os.environ.get("TEST_DB_USER") or os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("TEST_DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")
        host = os.environ.get("TEST_DB_HOST") or os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("TEST_DB_PORT") or os.environ.get("POSTGRES_PORT", "5433")
        # Always use test_mail_db unless explicitly overridden with TEST_DB_NAME
        database = os.environ.get("TEST_DB_NAME", "test_mail_db")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return db_url

# Skip all tests in this module if Postgres is not available
pytestmark = pytest.mark.skipif(
    not _is_postgres_available(),
    reason="PostgreSQL test database not available (set TEST_DATABASE_URL or start postgres on localhost:5433)"
)


# Fixtures for database connection
@pytest.fixture
def db_url():
    """Get test database URL from environment or use default.
    
    Uses a separate test database to avoid affecting real data.
    Default: test_mail_db (not mail_db)
    """
    return _get_test_db_url()


@pytest.fixture
def storage(db_url):
    """Create a PostgresStorage instance with test database."""
    storage = PostgresStorage(db_url=db_url)
    storage.init_db()
    
    # Clean up existing data - set FK to null first to avoid constraint violations
    conn = storage.connect()
    cur = conn.cursor()
    cur.execute("UPDATE messages SET latest_classification_id = NULL")
    cur.execute("DELETE FROM classifications")
    cur.execute("DELETE FROM messages")
    cur.execute("DELETE FROM metadata")
    conn.commit()
    cur.close()
    conn.close()
    
    yield storage
    
    # Cleanup after test - set FK to null first to avoid constraint violations
    conn = storage.connect()
    cur = conn.cursor()
    cur.execute("UPDATE messages SET latest_classification_id = NULL")
    cur.execute("DELETE FROM classifications")
    cur.execute("DELETE FROM messages")
    cur.execute("DELETE FROM metadata")
    conn.commit()
    cur.close()
    conn.close()


class TestPostgresStorageInit:
    """Tests for database initialization."""
    
    def test_init_db_creates_tables(self, storage):
        """Test that init_db creates all required tables."""
        conn = storage.connect()
        cur = conn.cursor()
        
        # Check messages table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'messages'
            )
        """)
        assert cur.fetchone()[0] is True
        
        # Check classifications table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'classifications'
            )
        """)
        assert cur.fetchone()[0] is True
        
        # Check metadata table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'metadata'
            )
        """)
        assert cur.fetchone()[0] is True
        
        cur.close()
        conn.close()
    
    def test_init_db_creates_indexes(self, storage):
        """Test that init_db creates necessary indexes."""
        conn = storage.connect()
        cur = conn.cursor()
        
        # Check for classification indexes
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE indexname = 'idx_classifications_message_id'
            )
        """)
        assert cur.fetchone()[0] is True
        
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE indexname = 'idx_classifications_created_at'
            )
        """)
        assert cur.fetchone()[0] is True
        
        cur.close()
        conn.close()


class TestPostgresStorageMessages:
    """Tests for message storage and retrieval."""
    
    def test_save_and_get_message(self, storage):
        """Test saving a message and retrieving it by ID."""
        msg = MailMessage(
            id="msg-001",
            subject="Test Subject",
            from_="sender@example.com",
            to="recipient@example.com",
            snippet="This is a test message",
            thread_id="thread-001",
            labels=["INBOX", "UNREAD"],
            internal_date=1234567890,
            has_attachments=False,
        )
        
        storage.save_message(msg)
        
        retrieved = storage.get_message_by_id("msg-001")
        assert retrieved is not None
        assert retrieved.id == "msg-001"
        assert retrieved.subject == "Test Subject"
        assert retrieved.from_ == "sender@example.com"
        assert retrieved.to == "recipient@example.com"
        assert retrieved.snippet == "This is a test message"
        assert retrieved.labels == ["INBOX", "UNREAD"]
        assert retrieved.has_attachments is False
    
    def test_save_message_with_attachments(self, storage):
        """Test saving a message with attachments."""
        msg = MailMessage(
            id="msg-002",
            subject="Message with attachment",
            from_="sender@example.com",
            has_attachments=True,
        )
        
        storage.save_message(msg)
        retrieved = storage.get_message_by_id("msg-002")
        assert retrieved.has_attachments is True
    
    def test_update_existing_message(self, storage):
        """Test that saving a message with same ID updates it."""
        msg1 = MailMessage(id="msg-003", subject="Original", from_="sender@example.com")
        storage.save_message(msg1)
        
        msg2 = MailMessage(id="msg-003", subject="Updated", from_="sender@example.com")
        storage.save_message(msg2)
        
        retrieved = storage.get_message_by_id("msg-003")
        assert retrieved.subject == "Updated"
    
    def test_get_message_ids(self, storage):
        """Test retrieving all message IDs."""
        msg1 = MailMessage(id="msg-101", subject="Test 1", from_="a@b.com")
        msg2 = MailMessage(id="msg-102", subject="Test 2", from_="c@d.com")
        msg3 = MailMessage(id="msg-103", subject="Test 3", from_="e@f.com")
        
        storage.save_message(msg1)
        storage.save_message(msg2)
        storage.save_message(msg3)
        
        ids = storage.get_message_ids()
        assert "msg-101" in ids
        assert "msg-102" in ids
        assert "msg-103" in ids
        assert len(ids) == 3
    
    def test_get_message_by_id_not_found(self, storage):
        """Test that getting a non-existent message returns None."""
        result = storage.get_message_by_id("nonexistent")
        assert result is None
    
    def test_list_messages(self, storage):
        """Test listing messages with pagination."""
        for i in range(5):
            msg = MailMessage(id=f"msg-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
        
        # Get first 3 messages
        messages = storage.list_messages(limit=3, offset=0)
        assert len(messages) == 3
        
        # Get next 2 messages
        messages = storage.list_messages(limit=3, offset=3)
        assert len(messages) == 2
    
    def test_save_message_with_complex_payload(self, storage):
        """Test saving message with complex JSON payload."""
        payload = {
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "SGVsbG8gV29ybGQ="}},
                {"mimeType": "text/html", "body": {"data": "PGgxPkhlbGxvPC9oMT4="}}
            ]
        }
        headers = {
            "From": "sender@example.com",
            "To": "recipient@example.com",
            "Subject": "Test"
        }
        
        msg = MailMessage(
            id="msg-payload",
            subject="Complex Payload",
            from_="sender@example.com",
            payload=payload,
            headers=headers
        )
        
        storage.save_message(msg)
        retrieved = storage.get_message_by_id("msg-payload")
        
        assert retrieved.payload == payload
        assert retrieved.headers == headers


class TestPostgresStorageClassifications:
    """Tests for classification storage and retrieval."""
    
    def test_create_classification(self, storage):
        """Test creating a classification for a message."""
        # First save a message
        msg = MailMessage(id="msg-class-001", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        # Create classification
        classification_id = storage.create_classification(
            message_id="msg-class-001",
            labels=["work", "urgent"],
            priority="high",
            summary="Important work email",
            model="gpt-4"
        )
        
        assert classification_id is not None
        assert len(classification_id) > 0
    
    def test_get_latest_classification(self, storage):
        """Test retrieving the latest classification for a message."""
        msg = MailMessage(id="msg-class-002", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        # Create first classification
        storage.create_classification(
            message_id="msg-class-002",
            labels=["personal"],
            priority="low",
            summary="First classification",
            model="gpt-3.5"
        )
        
        # Create second classification (should be the latest)
        storage.create_classification(
            message_id="msg-class-002",
            labels=["work", "urgent"],
            priority="high",
            summary="Second classification",
            model="gpt-4"
        )
        
        latest = storage.get_latest_classification("msg-class-002")
        assert latest is not None
        assert latest["labels"] == ["work", "urgent"]
        assert latest["priority"] == "high"
        assert latest["summary"] == "Second classification"
        assert latest["model"] == "gpt-4"
    
    def test_get_latest_classification_none(self, storage):
        """Test getting latest classification when none exists."""
        msg = MailMessage(id="msg-class-003", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        latest = storage.get_latest_classification("msg-class-003")
        assert latest is None
    
    def test_list_classification_records_for_message(self, storage):
        """Test listing all classifications for a message."""
        msg = MailMessage(id="msg-class-004", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        # Create multiple classifications
        storage.create_classification(
            message_id="msg-class-004",
            labels=["label1"],
            priority="low",
            summary="First"
        )
        storage.create_classification(
            message_id="msg-class-004",
            labels=["label2"],
            priority="medium",
            summary="Second"
        )
        storage.create_classification(
            message_id="msg-class-004",
            labels=["label3"],
            priority="high",
            summary="Third"
        )
        
        records = storage.list_classification_records_for_message("msg-class-004")
        assert len(records) == 3
        # Should be ordered by created_at DESC, so most recent first
        assert records[0].priority == "high"
        assert records[0].summary == "Third"
    
    def test_save_classification_record(self, storage):
        """Test saving a ClassificationRecord object."""
        msg = MailMessage(id="msg-class-005", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        record = ClassificationRecord(
            id="class-record-001",
            message_id="msg-class-005",
            labels=["important", "follow-up"],
            priority="high",
            summary="Important follow-up required",
            model="claude-3",
            created_at=datetime.now(timezone.utc)
        )
        
        storage.save_classification_record(record)
        
        records = storage.list_classification_records_for_message("msg-class-005")
        assert len(records) == 1
        assert records[0].id == "class-record-001"
        assert records[0].labels == ["important", "follow-up"]
        assert records[0].priority == "high"
        assert records[0].summary == "Important follow-up required"
    
    def test_get_unclassified_message_ids(self, storage):
        """Test getting IDs of unclassified messages."""
        # Create some messages
        msg1 = MailMessage(id="unclass-001", subject="Test 1", from_="sender@example.com")
        msg2 = MailMessage(id="unclass-002", subject="Test 2", from_="sender@example.com")
        msg3 = MailMessage(id="unclass-003", subject="Test 3", from_="sender@example.com")
        
        storage.save_message(msg1)
        storage.save_message(msg2)
        storage.save_message(msg3)
        
        # Classify only msg2
        storage.create_classification(
            message_id="unclass-002",
            labels=["work"],
            priority="medium",
            summary="Classified"
        )
        
        unclassified = storage.get_unclassified_message_ids()
        assert "unclass-001" in unclassified
        assert "unclass-002" not in unclassified
        assert "unclass-003" in unclassified
        assert len(unclassified) == 2
    
    def test_count_classified_messages(self, storage):
        """Test counting classified messages."""
        # Create messages
        for i in range(5):
            msg = MailMessage(id=f"count-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
        
        # Classify 3 of them
        for i in range(3):
            storage.create_classification(
                message_id=f"count-{i}",
                labels=["test"],
                priority="low",
                summary="Test"
            )
        
        count = storage.count_classified_messages()
        assert count == 3
    
    def test_get_message_with_classification(self, storage):
        """Test that getting a message includes its latest classification."""
        msg = MailMessage(id="msg-with-class", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        storage.create_classification(
            message_id="msg-with-class",
            labels=["important"],
            priority="high",
            summary="Test summary"
        )
        
        retrieved = storage.get_message_by_id("msg-with-class")
        assert retrieved.classification_labels == ["important"]
        assert retrieved.priority == "high"
        assert retrieved.summary == "Test summary"


class TestPostgresStorageMetadata:
    """Tests for metadata storage."""
    
    def test_set_and_get_history_id(self, storage):
        """Test storing and retrieving Gmail history ID."""
        storage.set_history_id("12345")
        history_id = storage.get_history_id()
        assert history_id == "12345"
    
    def test_update_history_id(self, storage):
        """Test updating an existing history ID."""
        storage.set_history_id("11111")
        storage.set_history_id("22222")
        history_id = storage.get_history_id()
        assert history_id == "22222"
    
    def test_get_history_id_none(self, storage):
        """Test getting history ID when none is set."""
        history_id = storage.get_history_id()
        assert history_id is None


class TestPostgresStorageSerialization:
    """Tests for JSON serialization/deserialization."""
    
    def test_serialize_deserialize_labels(self, storage):
        """Test that labels are properly serialized to JSONB."""
        msg = MailMessage(
            id="ser-001",
            subject="Test",
            from_="sender@example.com",
            labels=["INBOX", "IMPORTANT", "CATEGORY_PERSONAL"]
        )
        storage.save_message(msg)
        
        retrieved = storage.get_message_by_id("ser-001")
        assert retrieved.labels == ["INBOX", "IMPORTANT", "CATEGORY_PERSONAL"]
    
    def test_serialize_empty_labels(self, storage):
        """Test handling of empty labels list."""
        msg = MailMessage(
            id="ser-002",
            subject="Test",
            from_="sender@example.com",
            labels=[]
        )
        storage.save_message(msg)
        
        retrieved = storage.get_message_by_id("ser-002")
        assert retrieved.labels == []
    
    def test_serialize_none_labels(self, storage):
        """Test handling of None labels."""
        msg = MailMessage(
            id="ser-003",
            subject="Test",
            from_="sender@example.com",
            labels=None
        )
        storage.save_message(msg)
        
        retrieved = storage.get_message_by_id("ser-003")
        assert retrieved.labels is None


class TestPostgresStorageEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_message_with_special_characters(self, storage):
        """Test storing messages with special characters."""
        msg = MailMessage(
            id="special-001",
            subject="Test with émojis 🎉 and spëcial chârs",
            from_="sender@example.com",
            snippet="Contains quotes ' \" and backslashes \\"
        )
        storage.save_message(msg)
        
        retrieved = storage.get_message_by_id("special-001")
        assert retrieved.subject == "Test with émojis 🎉 and spëcial chârs"
        assert retrieved.snippet == "Contains quotes ' \" and backslashes \\"
    
    def test_large_message_payload(self, storage):
        """Test storing message with large payload."""
        large_body = "A" * 100000  # 100KB of data
        msg = MailMessage(
            id="large-001",
            subject="Large message",
            from_="sender@example.com",
            payload={"body": large_body}
        )
        storage.save_message(msg)
        
        retrieved = storage.get_message_by_id("large-001")
        assert retrieved.payload["body"] == large_body
    
    def test_concurrent_classification_creation(self, storage):
        """Test creating multiple classifications quickly."""
        msg = MailMessage(id="concurrent-001", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        
        # Create multiple classifications
        ids = []
        for i in range(5):
            class_id = storage.create_classification(
                message_id="concurrent-001",
                labels=[f"label-{i}"],
                priority="medium",
                summary=f"Classification {i}"
            )
            ids.append(class_id)
        
        # All IDs should be unique
        assert len(ids) == len(set(ids))
        
        # Should have 5 classification records
        records = storage.list_classification_records_for_message("concurrent-001")
        assert len(records) == 5


class TestPostgresStorageConnectionHandling:
    """Tests for database connection handling."""
    
    def test_connection_creates_successfully(self, db_url):
        """Test that connection can be established."""
        storage = PostgresStorage(db_url=db_url)
        conn = storage.connect()
        assert conn is not None
        conn.close()
    
    def test_multiple_operations_with_connection_pooling(self, storage):
        """Test that multiple operations work correctly."""
        # Perform multiple operations
        for i in range(10):
            msg = MailMessage(id=f"pool-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
        
        ids = storage.get_message_ids()
        assert len(ids) >= 10


@pytest.mark.skipif(
    not _is_postgres_available(),
    reason="PostgreSQL test database not available"
)
class TestPostgresStorageIntegration:
    """Integration tests that require actual PostgreSQL connection."""
    
    def test_full_workflow(self, storage):
        """Test a complete workflow: save message, classify, retrieve."""
        # Save a message
        msg = MailMessage(
            id="workflow-001",
            subject="Important Project Update",
            from_="boss@company.com",
            to="me@company.com",
            snippet="We need to discuss the Q4 roadmap",
            labels=["INBOX"],
            has_attachments=True
        )
        storage.save_message(msg)
        
        # Verify it's unclassified
        unclassified = storage.get_unclassified_message_ids()
        assert "workflow-001" in unclassified
        
        # Classify it
        classification_id = storage.create_classification(
            message_id="workflow-001",
            labels=["work", "urgent", "meeting"],
            priority="high",
            summary="Boss wants to discuss Q4 roadmap - schedule meeting",
            model="gpt-4"
        )
        
        # Verify it's now classified
        unclassified = storage.get_unclassified_message_ids()
        assert "workflow-001" not in unclassified
        
        # Get the message with classification
        retrieved = storage.get_message_by_id("workflow-001")
        assert retrieved.classification_labels == ["work", "urgent", "meeting"]
        assert retrieved.priority == "high"
        assert "Q4 roadmap" in retrieved.summary
        
        # Get latest classification directly
        latest = storage.get_latest_classification("workflow-001")
        assert latest["id"] == classification_id
        assert latest["model"] == "gpt-4"
        
        # List all messages
        messages = storage.list_messages(limit=10)
        assert any(m.id == "workflow-001" for m in messages)


class TestPostgresStorageMetadataOperations:
    """Extended tests for metadata operations."""
    
    def test_history_id_roundtrip(self, storage):
        """Test complete history ID lifecycle."""
        # Should start as None
        assert storage.get_history_id() is None
        
        # Set first value
        storage.set_history_id("abc-123")
        assert storage.get_history_id() == "abc-123"
        
        # Update to new value (upsert behavior)
        storage.set_history_id("def-456")
        assert storage.get_history_id() == "def-456"
        
        # Update again
        storage.set_history_id("xyz-789")
        assert storage.get_history_id() == "xyz-789"
    
    def test_history_id_with_special_characters(self, storage):
        """Test history ID with various special characters."""
        special_id = "hist-123_abc.def@2024"
        storage.set_history_id(special_id)
        assert storage.get_history_id() == special_id


class TestPostgresStorageLargePayloads:
    """Tests for handling large message payloads."""
    
    def _make_large_payload(self, size_mb: float = 2.0) -> dict:
        """Generate a large payload of approximately size_mb megabytes."""
        # Create a string that's roughly 1KB
        chunk = "x" * 1024
        # Calculate how many chunks we need
        num_chunks = int((size_mb * 1024 * 1024) / len(chunk))
        return {
            "type": "large_payload_test",
            "data": [chunk for _ in range(num_chunks)],
            "metadata": {
                "size_mb": size_mb,
                "num_chunks": num_chunks
            }
        }
    
    def test_large_payload_2mb(self, storage):
        """Test storing and retrieving a 2MB payload."""
        payload = self._make_large_payload(2.0)
        payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        original_hash = hashlib.sha256(payload_bytes).hexdigest()
        original_size = len(payload_bytes)
        
        msg = MailMessage(
            id="large-2mb",
            subject="Large payload test",
            from_="sender@example.com",
            payload=payload,
            has_attachments=False,
        )
        
        storage.save_message(msg)
        retrieved = storage.get_message_by_id("large-2mb")
        
        assert retrieved is not None
        assert retrieved.payload is not None
        
        # Verify content integrity using hash (with sorted keys for consistent comparison)
        roundtrip_bytes = json.dumps(retrieved.payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        roundtrip_hash = hashlib.sha256(roundtrip_bytes).hexdigest()
        
        assert roundtrip_hash == original_hash
        assert len(roundtrip_bytes) == original_size
    
    def test_large_payload_5mb(self, storage):
        """Test storing and retrieving a 5MB payload."""
        payload = self._make_large_payload(5.0)
        payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        original_hash = hashlib.sha256(payload_bytes).hexdigest()
        
        msg = MailMessage(
            id="large-5mb",
            subject="Very large payload test",
            from_="sender@example.com",
            payload=payload,
            has_attachments=True,
        )
        
        storage.save_message(msg)
        retrieved = storage.get_message_by_id("large-5mb")
        
        assert retrieved is not None
        roundtrip_bytes = json.dumps(retrieved.payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        roundtrip_hash = hashlib.sha256(roundtrip_bytes).hexdigest()
        
        assert roundtrip_hash == original_hash
        assert retrieved.has_attachments is True
    
    def test_nested_large_payload(self, storage):
        """Test deeply nested large payload structure."""
        # Create a deeply nested structure
        nested_payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "data": ["x" * 10000 for _ in range(100)],
                            "metadata": {
                                "nested": True,
                                "depth": 4
                            }
                        }
                    }
                }
            }
        }
        
        msg = MailMessage(
            id="nested-large",
            subject="Nested large payload",
            from_="sender@example.com",
            payload=nested_payload,
        )
        
        storage.save_message(msg)
        retrieved = storage.get_message_by_id("nested-large")
        
        assert retrieved is not None
        assert retrieved.payload["level1"]["level2"]["level3"]["level4"]["metadata"]["depth"] == 4
        assert len(retrieved.payload["level1"]["level2"]["level3"]["level4"]["data"]) == 100
    
    def test_multiple_large_messages(self, storage):
        """Test storing multiple large messages."""
        messages_to_create = 5
        
        for i in range(messages_to_create):
            payload = self._make_large_payload(1.0)  # 1MB each
            msg = MailMessage(
                id=f"bulk-large-{i}",
                subject=f"Bulk test {i}",
                from_="sender@example.com",
                payload=payload,
            )
            storage.save_message(msg)
        
        # Verify all can be retrieved
        for i in range(messages_to_create):
            retrieved = storage.get_message_by_id(f"bulk-large-{i}")
            assert retrieved is not None
            assert retrieved.payload["type"] == "large_payload_test"
        
        # Verify list_messages works with large payloads
        messages = storage.list_messages(limit=10)
        large_messages = [m for m in messages if m.id.startswith("bulk-large-")]
        assert len(large_messages) == messages_to_create


class TestPostgresStorageFilteringOptimization:
    """Tests for the optimized list_messages_by_filters method."""
    
    def test_filter_by_priority_only(self, storage):
        """Test filtering by priority only."""
        # Create messages with different priorities
        for i in range(10):
            msg = MailMessage(id=f"filter-priority-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            
            if i < 3:
                priority = "high"
            elif i < 6:
                priority = "normal"
            else:
                priority = "low"
            
            storage.create_classification(
                message_id=f"filter-priority-{i}",
                labels=["test"],
                priority=priority,
                summary=f"Test message {i}"
            )
        
        # Filter by high priority
        messages, total = storage.list_messages_by_filters(priority="high", limit=10, offset=0)
        assert len(messages) == 3
        assert total == 3
        assert all(m.priority == "high" for m in messages)
        
        # Filter by normal priority
        messages, total = storage.list_messages_by_filters(priority="normal", limit=10, offset=0)
        assert len(messages) == 3
        assert total == 3
        assert all(m.priority == "normal" for m in messages)
    
    def test_filter_by_single_label(self, storage):
        """Test filtering by a single label."""
        # Create messages with different labels
        for i in range(5):
            msg = MailMessage(id=f"filter-label-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            
            labels = ["work"] if i % 2 == 0 else ["personal"]
            storage.create_classification(
                message_id=f"filter-label-{i}",
                labels=labels,
                priority="normal",
                summary=f"Test {i}"
            )
        
        # Filter by work label
        messages, total = storage.list_messages_by_filters(labels=["work"], limit=10, offset=0)
        assert len(messages) == 3  # 0, 2, 4
        assert total == 3
        assert all("work" in m.classification_labels for m in messages)
        
        # Filter by personal label
        messages, total = storage.list_messages_by_filters(labels=["personal"], limit=10, offset=0)
        assert len(messages) == 2  # 1, 3
        assert total == 2
        assert all("personal" in m.classification_labels for m in messages)
    
    def test_filter_by_multiple_labels(self, storage):
        """Test filtering by multiple labels (AND logic)."""
        # Create messages with various label combinations
        test_cases = [
            ("multi-label-0", ["work", "urgent"]),
            ("multi-label-1", ["work", "urgent", "important"]),
            ("multi-label-2", ["work"]),
            ("multi-label-3", ["urgent"]),
            ("multi-label-4", ["personal", "urgent"]),
        ]
        
        for msg_id, labels in test_cases:
            msg = MailMessage(id=msg_id, subject="Test", from_="sender@example.com")
            storage.save_message(msg)
            storage.create_classification(
                message_id=msg_id,
                labels=labels,
                priority="normal",
                summary="Test"
            )
        
        # Filter by work AND urgent (should match multi-label-0 and multi-label-1)
        messages, total = storage.list_messages_by_filters(labels=["work", "urgent"], limit=10, offset=0)
        assert len(messages) == 2
        assert total == 2
        ids = {m.id for m in messages}
        assert ids == {"multi-label-0", "multi-label-1"}
        
        # Filter by work AND urgent AND important (should match only multi-label-1)
        messages, total = storage.list_messages_by_filters(
            labels=["work", "urgent", "important"], 
            limit=10, 
            offset=0
        )
        assert len(messages) == 1
        assert total == 1
        assert messages[0].id == "multi-label-1"
    
    def test_filter_by_priority_and_labels(self, storage):
        """Test filtering by both priority and labels."""
        # Create messages with combinations
        test_cases = [
            ("combo-0", "high", ["work", "urgent"]),
            ("combo-1", "high", ["personal"]),
            ("combo-2", "normal", ["work", "urgent"]),
            ("combo-3", "low", ["work"]),
        ]
        
        for msg_id, priority, labels in test_cases:
            msg = MailMessage(id=msg_id, subject="Test", from_="sender@example.com")
            storage.save_message(msg)
            storage.create_classification(
                message_id=msg_id,
                labels=labels,
                priority=priority,
                summary="Test"
            )
        
        # Filter by high priority AND work label
        messages, total = storage.list_messages_by_filters(
            priority="high",
            labels=["work"],
            limit=10,
            offset=0
        )
        assert len(messages) == 1
        assert total == 1
        assert messages[0].id == "combo-0"
        
        # Filter by work AND urgent labels (any priority)
        messages, total = storage.list_messages_by_filters(
            labels=["work", "urgent"],
            limit=10,
            offset=0
        )
        assert len(messages) == 2
        assert total == 2
        ids = {m.id for m in messages}
        assert ids == {"combo-0", "combo-2"}
    
    def test_filter_classified_only(self, storage):
        """Test filtering only classified messages."""
        # Create some classified and unclassified messages
        for i in range(5):
            msg = MailMessage(id=f"classified-test-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            
            # Classify only even-numbered messages
            if i % 2 == 0:
                storage.create_classification(
                    message_id=f"classified-test-{i}",
                    labels=["test"],
                    priority="normal",
                    summary="Classified"
                )
        
        # Filter classified only
        messages, total = storage.list_messages_by_filters(classified=True, limit=10, offset=0)
        assert len(messages) == 3  # 0, 2, 4
        assert total == 3
        assert all(m.classification_labels is not None for m in messages)
    
    def test_filter_unclassified_only(self, storage):
        """Test filtering only unclassified messages."""
        # Create some classified and unclassified messages
        for i in range(5):
            msg = MailMessage(id=f"unclassified-test-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            
            # Classify only even-numbered messages
            if i % 2 == 0:
                storage.create_classification(
                    message_id=f"unclassified-test-{i}",
                    labels=["test"],
                    priority="normal",
                    summary="Classified"
                )
        
        # Filter unclassified only
        messages, total = storage.list_messages_by_filters(classified=False, limit=10, offset=0)
        assert len(messages) == 2  # 1, 3
        assert total == 2
        assert all(m.classification_labels is None for m in messages)
    
    def test_filter_with_pagination(self, storage):
        """Test filtering with pagination."""
        # Create 20 messages with same priority
        for i in range(20):
            msg = MailMessage(id=f"page-test-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            storage.create_classification(
                message_id=f"page-test-{i}",
                labels=["test"],
                priority="high",
                summary="Test"
            )
        
        # Get first page (5 messages)
        messages, total = storage.list_messages_by_filters(priority="high", limit=5, offset=0)
        assert len(messages) == 5
        assert total == 20
        
        # Get second page (5 messages)
        messages, total = storage.list_messages_by_filters(priority="high", limit=5, offset=5)
        assert len(messages) == 5
        assert total == 20
        
        # Get last page (remaining 5 messages)
        messages, total = storage.list_messages_by_filters(priority="high", limit=5, offset=15)
        assert len(messages) == 5
        assert total == 20
        
        # Beyond last page
        messages, total = storage.list_messages_by_filters(priority="high", limit=5, offset=20)
        assert len(messages) == 0
        assert total == 20
    
    def test_filter_no_matches(self, storage):
        """Test filtering with no matching messages."""
        # Create some messages
        for i in range(3):
            msg = MailMessage(id=f"nomatch-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            storage.create_classification(
                message_id=f"nomatch-{i}",
                labels=["work"],
                priority="low",
                summary="Test"
            )
        
        # Filter by non-existent label
        messages, total = storage.list_messages_by_filters(labels=["nonexistent"], limit=10, offset=0)
        assert len(messages) == 0
        assert total == 0
        
        # Filter by non-existent priority
        messages, total = storage.list_messages_by_filters(priority="critical", limit=10, offset=0)
        assert len(messages) == 0
        assert total == 0
    
    def test_filter_all_parameters(self, storage):
        """Test filtering with all parameters combined."""
        # Create a variety of messages
        test_cases = [
            ("all-params-0", "high", ["work", "urgent", "important"], True),
            ("all-params-1", "high", ["work", "urgent"], True),
            ("all-params-2", "normal", ["work", "urgent", "important"], True),
            ("all-params-3", "high", ["personal"], True),
            ("all-params-4", None, None, False),  # Unclassified
        ]
        
        for msg_id, priority, labels, is_classified in test_cases:
            msg = MailMessage(id=msg_id, subject="Test", from_="sender@example.com")
            storage.save_message(msg)
            
            if is_classified:
                storage.create_classification(
                    message_id=msg_id,
                    labels=labels,
                    priority=priority,
                    summary="Test"
                )
        
        # Filter: high priority + work label + urgent label + classified only
        messages, total = storage.list_messages_by_filters(
            priority="high",
            labels=["work", "urgent"],
            classified=True,
            limit=10,
            offset=0
        )
        assert len(messages) == 2
        assert total == 2
        ids = {m.id for m in messages}
        assert ids == {"all-params-0", "all-params-1"}
    
    def test_filter_case_insensitivity(self, storage):
        """Test that priority filtering is case-insensitive."""
        msg = MailMessage(id="case-test", subject="Test", from_="sender@example.com")
        storage.save_message(msg)
        storage.create_classification(
            message_id="case-test",
            labels=["test"],
            priority="High",  # Mixed case
            summary="Test"
        )
        
        # Should match regardless of case
        for priority_variant in ["high", "HIGH", "High", "HiGh"]:
            messages, total = storage.list_messages_by_filters(priority=priority_variant, limit=10, offset=0)
            assert len(messages) == 1
            assert total == 1
            assert messages[0].id == "case-test"
    
    def test_filter_empty_labels_list(self, storage):
        """Test filtering with empty labels list (should return all classified)."""
        for i in range(3):
            msg = MailMessage(id=f"empty-labels-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            storage.create_classification(
                message_id=f"empty-labels-{i}",
                labels=["test"],
                priority="normal",
                summary="Test"
            )
        
        # Empty labels list should not filter by labels
        messages, total = storage.list_messages_by_filters(labels=[], limit=10, offset=0)
        assert len(messages) == 3
        assert total == 3
    
    def test_filter_performance_large_dataset(self, storage):
        """Test filtering performance with larger dataset."""
        # Create 100 messages with various combinations
        for i in range(100):
            msg = MailMessage(id=f"perf-{i}", subject=f"Test {i}", from_="sender@example.com")
            storage.save_message(msg)
            
            priority = ["high", "normal", "low"][i % 3]
            labels = [["work"], ["personal"], ["work", "urgent"]][i % 3]
            
            storage.create_classification(
                message_id=f"perf-{i}",
                labels=labels,
                priority=priority,
                summary=f"Test {i}"
            )
        
        import time
        
        # Test filter speed - should be fast with indexes
        start = time.time()
        messages, total = storage.list_messages_by_filters(
            priority="high",
            labels=["work"],
            limit=50,
            offset=0
        )
        elapsed = time.time() - start
        
        # Should complete quickly (under 1 second even for 100 messages)
        assert elapsed < 1.0
        assert total > 0  # Should find some matches
        assert len(messages) <= 50  # Respects limit
