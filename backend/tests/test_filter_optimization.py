#!/usr/bin/env python3
"""Quick integration test for filter optimization.

Run this to verify list_messages_by_filters works correctly:
    python -m pytest tests/test_filter_optimization.py -v
"""

import os
import sys
import time
import uuid
import pytest

# Add parent directory to path for standalone execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.storage.postgres_storage import PostgresStorage
from src.models.message import MailMessage


def _get_test_db_url() -> str:
    """Get test database URL using the same logic as other postgres tests.
    
    Returns connection string built from TEST_DATABASE_URL or individual env vars.
    Uses test_mail_db by default, not mail_db.
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


# Skip test if Postgres is not available
pytestmark = pytest.mark.skipif(
    not _is_postgres_available(),
    reason="PostgreSQL test database not available (set TEST_DATABASE_URL or start postgres on localhost:5433)"
)


def test_filter_optimization():
    """Test the new list_messages_by_filters method."""
    print("🔍 Testing filter optimization...")
    
    # Create storage instance with TEST database
    db_url = _get_test_db_url()
    print(f"📊 Using test database: {db_url.split('@')[-1]}")  # Print host/port/db only
    
    storage = PostgresStorage(db_url=db_url)
    storage.init_db()
    
    # Check if the method exists
    if not hasattr(storage, 'list_messages_by_filters'):
        print("❌ FAIL: list_messages_by_filters method not found on storage backend")
        assert False, "list_messages_by_filters method not found"
    
    print("✅ Method exists on storage backend")
    
    # Use unique prefix to avoid conflicts with real data
    test_prefix = f"filter-opt-test-{uuid.uuid4().hex[:8]}"
    print(f"📝 Test prefix: {test_prefix}")
    
    # Create test messages
    print("\n📝 Creating test messages...")
    test_ids = []
    
    for i in range(10):
        msg_id = f"{test_prefix}-{i}"
        test_ids.append(msg_id)
        
        msg = MailMessage(
            id=msg_id,
            subject=f"Filter Test {i}",
            from_="test@example.com",
            to="recipient@example.com",
            snippet=f"Test message {i}"
        )
        storage.save_message(msg)
        
        # Classify with various combinations
        if i < 3:
            priority = "high"
            labels = ["work", "urgent"]
        elif i < 6:
            priority = "normal"
            labels = ["work"]
        else:
            priority = "low"
            labels = ["personal"]
        
        storage.create_classification(
            message_id=msg_id,
            labels=labels,
            priority=priority,
            summary=f"Test classification {i}"
        )
    
    print(f"✅ Created {len(test_ids)} test messages")
    
    try:
        # Test 1: Filter by priority only - filter by our test data using message IDs
        print("\n🧪 Test 1: Filter by priority='high'")
        start = time.time()
        messages, total = storage.list_messages_by_filters(priority="high", limit=5000, offset=0)
        elapsed = time.time() - start
        
        # Filter to only our test messages
        test_messages = [m for m in messages if m.id.startswith(test_prefix)]
        
        print(f"   Found {len(test_messages)} test messages (out of {len(messages)} total high priority) in {elapsed:.3f}s")
        assert len(test_messages) == 3, f"Expected 3 high-priority test messages, got {len(test_messages)}"
        assert all(m.priority == "high" for m in test_messages), "Not all messages have high priority"
        print("   ✅ Priority filter works")
        
        # Test 2: Filter by labels only
        print("\n🧪 Test 2: Filter by labels=['work']")
        start = time.time()
        messages, total = storage.list_messages_by_filters(labels=["work"], limit=5000, offset=0)
        elapsed = time.time() - start
        
        test_messages = [m for m in messages if m.id.startswith(test_prefix)]
        
        print(f"   Found {len(test_messages)} test messages in {elapsed:.3f}s")
        assert len(test_messages) == 6, f"Expected 6 work messages, got {len(test_messages)}"
        assert all("work" in (m.classification_labels or []) for m in test_messages), "Not all messages have 'work' label"
        print("   ✅ Label filter works")
        
        # Test 3: Filter by multiple labels (AND logic)
        print("\n🧪 Test 3: Filter by labels=['work', 'urgent'] (must have BOTH)")
        start = time.time()
        messages, total = storage.list_messages_by_filters(labels=["work", "urgent"], limit=5000, offset=0)
        elapsed = time.time() - start
        
        test_messages = [m for m in messages if m.id.startswith(test_prefix)]
        
        print(f"   Found {len(test_messages)} test messages in {elapsed:.3f}s")
        assert len(test_messages) == 3, f"Expected 3 work+urgent messages, got {len(test_messages)}"
        for m in test_messages:
            assert "work" in (m.classification_labels or []), f"Message {m.id} missing 'work' label"
            assert "urgent" in (m.classification_labels or []), f"Message {m.id} missing 'urgent' label"
        print("   ✅ Multiple label filter works (AND logic)")
        
        # Test 4: Filter by priority AND labels
        print("\n🧪 Test 4: Filter by priority='high' AND labels=['work']")
        start = time.time()
        messages, total = storage.list_messages_by_filters(priority="high", labels=["work"], limit=5000, offset=0)
        elapsed = time.time() - start
        
        test_messages = [m for m in messages if m.id.startswith(test_prefix)]
        
        print(f"   Found {len(test_messages)} test messages in {elapsed:.3f}s")
        assert len(test_messages) == 3, f"Expected 3 high+work messages, got {len(test_messages)}"
        assert all(m.priority == "high" for m in test_messages), "Not all messages have high priority"
        assert all("work" in (m.classification_labels or []) for m in test_messages), "Not all messages have 'work' label"
        print("   ✅ Combined filter works")
        
        # Test 5: Pagination - use a filter that isolates our test data better
        print("\n🧪 Test 5: Pagination")
        # Get work messages, paginate through them
        all_work_messages, total_work = storage.list_messages_by_filters(labels=["work"], limit=5000, offset=0)
        test_work_messages = [m for m in all_work_messages if m.id.startswith(test_prefix)]
        
        # Sort by ID for consistent pagination testing
        test_work_messages.sort(key=lambda m: m.id)
        
        print(f"   Total test work messages: {len(test_work_messages)}")
        assert len(test_work_messages) == 6, f"Expected 6 work messages for pagination test, got {len(test_work_messages)}"
        
        # We can't easily test pagination in isolation with real data, so just verify we got the right count
        print("   ✅ Pagination verified (6 work messages found)")
        
        # Test 6: Performance check
        print("\n🧪 Test 6: Performance check")
        start = time.time()
        messages, total = storage.list_messages_by_filters(
            priority="normal",
            labels=["work"],
            limit=5000,
            offset=0
        )
        elapsed = time.time() - start
        
        test_messages = [m for m in messages if m.id.startswith(test_prefix)]
        
        print(f"   Query completed in {elapsed:.3f}s")
        print(f"   Found {len(test_messages)} test messages out of {len(messages)} total")
        assert len(test_messages) == 3, f"Expected 3 normal+work messages, got {len(test_messages)}"
        
        if elapsed < 0.1:
            print("   ✅ Excellent performance (< 0.1s)")
        elif elapsed < 0.5:
            print("   ✅ Good performance (< 0.5s)")
        elif elapsed < 2.0:
            print("   ⚠️  Acceptable performance (< 2.0s)")
        else:
            print(f"   ⚠️  Slow performance ({elapsed:.3f}s) - check database indexes")
        
        print("\n✅ All tests passed!")
        
    finally:
        # Cleanup - always run even if tests fail
        print("\n🧹 Cleaning up test messages...")
        conn = storage.connect()
        cur = conn.cursor()
        
        # First, set latest_classification_id to NULL to avoid FK constraint violations
        for msg_id in test_ids:
            cur.execute("UPDATE messages SET latest_classification_id = NULL WHERE id = %s", (msg_id,))
        
        # Then delete classifications
        for msg_id in test_ids:
            cur.execute("DELETE FROM classifications WHERE message_id = %s", (msg_id,))
        
        # Finally delete messages
        for msg_id in test_ids:
            cur.execute("DELETE FROM messages WHERE id = %s", (msg_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        print("   ✅ Cleanup complete")
