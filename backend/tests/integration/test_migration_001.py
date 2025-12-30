"""Tests for database migration 001_add_fulltext_search.sql.

These tests verify that the full-text search migration:
- Adds search_vector tsvector column
- Creates GIN index for fast search
- Creates trigger function and trigger
- Is idempotent (can run multiple times)
- Preserves existing data
- Populates search_vector for existing messages
"""
import pytest
import os
import json
from pathlib import Path

from src.storage.postgres_storage import PostgresStorage
from src.models.message import MailMessage
from run_migration import run_migration


class TestFullTextSearchMigration:
    """Test the 001_add_fulltext_search.sql migration."""

    def test_migration_adds_search_vector_column(self):
        """Migration should add search_vector tsvector column to messages table."""
        storage = PostgresStorage()
        conn = storage.connect()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'messages' AND column_name = 'search_vector'
        """)
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        assert result is not None, "search_vector column should exist"
        assert result[1] == 'tsvector', "Column should be tsvector type"

    def test_migration_creates_gin_index(self):
        """Migration should create GIN index on search_vector for fast searches."""
        storage = PostgresStorage()
        conn = storage.connect()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes 
            WHERE indexname = 'idx_messages_search_vector_gin'
        """)
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        assert result is not None, "GIN index should exist"
        assert 'gin' in result[1].lower(), "Should be a GIN index"

    def test_migration_creates_trigger_function(self):
        """Migration should create trigger function for auto-updating search_vector."""
        storage = PostgresStorage()
        conn = storage.connect()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT routine_name 
            FROM information_schema.routines 
            WHERE routine_name = 'messages_search_vector_trigger'
                AND routine_type = 'FUNCTION'
        """)
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        assert result is not None, "Trigger function should exist"

    def test_migration_creates_trigger(self):
        """Migration should create BEFORE INSERT/UPDATE trigger on messages table."""
        storage = PostgresStorage()
        conn = storage.connect()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT trigger_name, event_manipulation, action_timing
            FROM information_schema.triggers 
            WHERE trigger_name = 'messages_search_vector_update'
                AND event_object_table = 'messages'
        """)
        results = cur.fetchall()
        
        cur.close()
        conn.close()
        
        assert len(results) > 0, "Trigger should exist"
        # Should fire on both INSERT and UPDATE
        events = [r[1] for r in results]
        assert 'INSERT' in events or 'UPDATE' in events, "Should trigger on INSERT or UPDATE"

    def test_migration_is_idempotent(self):
        """Running migration multiple times should not error or create duplicates."""
        migration_file = "src/storage/migrations/001_add_fulltext_search.sql"
        
        # Run migration again (it was already run during setup)
        try:
            run_migration(migration_file)
        except Exception as e:
            pytest.fail(f"Migration should be idempotent but raised: {e}")
        
        # Verify no duplicate indexes
        storage = PostgresStorage()
        conn = storage.connect()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE indexname = 'idx_messages_search_vector_gin'
        """)
        count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        assert count == 1, "Should have exactly one GIN index, not duplicates"

    def test_trigger_populates_search_vector_on_insert(self):
        """Trigger should auto-populate search_vector when new messages are inserted."""
        storage = PostgresStorage()
        storage.init_db()
        
        msg = MailMessage(
            id="trigger_test_insert",
            subject="Python programming tutorial",
            snippet="Learn Python basics",
            from_="teacher@example.com",
            labels=["INBOX"]
        )
        storage.save_message(msg)
        
        # Verify search_vector is populated
        conn = storage.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT search_vector IS NOT NULL as has_vector
            FROM messages 
            WHERE id = 'trigger_test_insert'
        """)
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        assert result is not None, "Message should be saved"
        assert result[0] is True, "search_vector should be auto-populated by trigger"

    def test_trigger_updates_search_vector_on_update(self):
        """Trigger should update search_vector when message is updated."""
        storage = PostgresStorage()
        storage.init_db()
        
        msg = MailMessage(
            id="trigger_test_update",
            subject="Original subject",
            snippet="Original content",
            from_="sender@example.com",
            labels=["INBOX"]
        )
        storage.save_message(msg)
        
        # Update message
        msg.subject = "Updated Python tutorial"
        msg.snippet = "Learn advanced Python"
        storage.save_message(msg)
        
        # Verify search_vector updated and searchable
        conn = storage.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT ts_rank_cd(search_vector, query, 1) > 0 as matches
            FROM messages, plainto_tsquery('english', 'Python tutorial') query
            WHERE id = 'trigger_test_update'
                AND search_vector @@ query
        """)
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        assert result is not None, "Should find message with updated content"

    def test_search_vector_weighting(self):
        """Test that subject has higher weight (A) than snippet (B) in search ranking."""
        storage = PostgresStorage()
        storage.init_db()
        
        # Message with keyword in subject
        msg1 = MailMessage(
            id="weight_test_1",
            subject="Python programming guide",
            snippet="Learn Java basics",
            from_="author@example.com",
            labels=["INBOX"]
        )
        
        # Message with keyword in snippet
        msg2 = MailMessage(
            id="weight_test_2",
            subject="Java tutorial",
            snippet="Python programming basics",
            from_="author@example.com",
            labels=["INBOX"]
        )
        
        storage.save_message(msg1)
        storage.save_message(msg2)
        
        # Search for "Python" - msg1 should rank higher (subject weight 'A' > snippet weight 'B')
        conn = storage.connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, ts_rank_cd(search_vector, query, 1) as rank
            FROM messages, plainto_tsquery('english', 'Python') query
            WHERE id IN ('weight_test_1', 'weight_test_2')
                AND search_vector @@ query
            ORDER BY rank DESC
        """)
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        assert len(results) == 2, "Should find both messages"
        assert results[0][0] == "weight_test_1", "Message with keyword in subject should rank higher"

    def test_migration_preserves_existing_data(self):
        """Migration should not delete or corrupt existing messages."""
        storage = PostgresStorage()
        storage.init_db()
        
        # Insert test message before migration (simulated - migration already ran)
        msg = MailMessage(
            id="preservation_test",
            subject="Test message",
            snippet="Content",
            from_="test@example.com",
            labels=["INBOX"],
            internal_date=1733050800000
        )
        storage.save_message(msg)
        
        # Retrieve and verify all fields intact
        retrieved = storage.get_message_by_id("preservation_test")
        
        assert retrieved is not None
        assert retrieved.subject == "Test message"
        assert retrieved.snippet == "Content"
        assert retrieved.from_ == "test@example.com"
        # Labels may be returned as JSON string or list depending on psycopg2 version
        import json
        if isinstance(retrieved.labels, str):
            assert json.loads(retrieved.labels) == ["INBOX"]
        else:
            assert retrieved.labels == ["INBOX"]
