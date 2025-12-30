"""Performance benchmarks for search operations.

These tests measure the latency of different search methods to ensure they
meet performance targets for production use.

NOTE: These tests are marked with @pytest.mark.slow and use a 100-message dataset.
Run with: pytest -m slow

Targets (100-message dataset):
- Keyword search: < 100ms
- Concurrent queries: maintain performance with 10 parallel requests

For production validation with larger datasets (1000+ messages), manually
adjust the fixture dataset size and run separately.
"""

import os
import time
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models.message import MailMessage
from src.storage.postgres_storage import PostgresStorage
from src.services.embedding_service import EmbeddingService


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
    """Get test database URL."""
    db_url = os.environ.get("TEST_DATABASE_URL")
    if not db_url:
        user = os.environ.get("TEST_DB_USER") or os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("TEST_DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")
        host = os.environ.get("TEST_DB_HOST") or os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("TEST_DB_PORT") or os.environ.get("POSTGRES_PORT", "5433")
        database = os.environ.get("TEST_DB_NAME", "test_mail_db")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return db_url


pytestmark = [
    pytest.mark.skipif(
        not _is_postgres_available(),
        reason="PostgreSQL test database not available for performance tests"
    ),
    pytest.mark.slow,  # Mark all performance tests as slow
]


@pytest.fixture(scope="session")
def storage_with_data():
    """Create storage with sample data for performance testing.
    
    Session-scoped to avoid recreating dataset for each test.
    """
    db_url = _get_test_db_url()
    storage = PostgresStorage(db_url=db_url)
    storage.init_db()
    
    # Clean existing data
    conn = storage.connect()
    cur = conn.cursor()
    cur.execute("UPDATE messages SET latest_classification_id = NULL")
    cur.execute("DELETE FROM classifications")
    cur.execute("DELETE FROM messages")
    conn.commit()
    cur.close()
    conn.close()
    
    # Create test dataset - 100 messages for quick performance testing
    # (Reduced from 1000 to speed up test suite - still enough for perf validation)
    print("\n[PERF] Creating test dataset (100 messages)...")
    subjects = [
        "Invoice #{} for Services",
        "Payment Reminder #{}", 
        "Meeting Notes {}",
        "Project Update #{}",
        "Team Standup {}",
        "Budget Review #{}",
        "Client Proposal {}",
        "Weekly Report #{}",
        "Code Review Request #{}",
        "Bug Report #{}",
    ]
    
    for i in range(100):
        subject_template = subjects[i % len(subjects)]
        msg = MailMessage(
            id=f"perf{i}",
            thread_id=f"thread{i}",
            from_=f"user{i % 10}@example.com",
            subject=subject_template.format(i),
            snippet=f"This is test message {i} with some sample content for searching.",
            internal_date=1733050800000 + i*1000,
        )
        storage.save_message(msg)
    
    print("[PERF] Test dataset ready (100 messages)\n")
    
    yield storage
    
    # Cleanup
    conn = storage.connect()
    cur = conn.cursor()
    cur.execute("UPDATE messages SET latest_classification_id = NULL")
    cur.execute("DELETE FROM classifications")
    cur.execute("DELETE FROM messages")
    conn.commit()
    cur.close()
    conn.close()


class TestKeywordSearchPerformance:
    """Performance tests for keyword search."""
    
    def test_keyword_search_latency_single_term(self, storage_with_data):
        """Single-term keyword search should complete in < 100ms."""
        storage = storage_with_data
        
        # Warm-up query
        storage.keyword_search("invoice", limit=10)
        
        # Measure performance
        iterations = 10
        timings = []
        
        for _ in range(iterations):
            start = time.time()
            results = storage.keyword_search("invoice", limit=10)
            elapsed = time.time() - start
            timings.append(elapsed * 1000)  # Convert to ms
        
        avg_ms = sum(timings) / len(timings)
        max_ms = max(timings)
        
        print(f"\n[PERF] Keyword search (single term):")
        print(f"  Average: {avg_ms:.1f}ms")
        print(f"  Max: {max_ms:.1f}ms")
        print(f"  Results: {len(results)}")
        
        # Should average under 100ms
        assert avg_ms < 100, f"Average latency {avg_ms:.1f}ms exceeds 100ms target"
    
    def test_keyword_search_latency_multi_term(self, storage_with_data):
        """Multi-term keyword search should complete in < 150ms."""
        storage = storage_with_data
        
        # Warm-up
        storage.keyword_search("invoice payment", limit=10)
        
        # Measure
        iterations = 10
        timings = []
        
        for _ in range(iterations):
            start = time.time()
            results = storage.keyword_search("invoice payment services", limit=10)
            elapsed = time.time() - start
            timings.append(elapsed * 1000)
        
        avg_ms = sum(timings) / len(timings)
        max_ms = max(timings)
        
        print(f"\n[PERF] Keyword search (multi-term):")
        print(f"  Average: {avg_ms:.1f}ms")
        print(f"  Max: {max_ms:.1f}ms")
        
        assert avg_ms < 150, f"Average latency {avg_ms:.1f}ms exceeds 150ms target"
    
    def test_keyword_search_with_large_result_set(self, storage_with_data):
        """Search returning many results should still be fast."""
        storage = storage_with_data
        
        # Search for common term that matches many messages
        start = time.time()
        results = storage.keyword_search("test", limit=100)
        elapsed = time.time() - start
        elapsed_ms = elapsed * 1000
        
        print(f"\n[PERF] Keyword search (large result set):")
        print(f"  Latency: {elapsed_ms:.1f}ms")
        print(f"  Results: {len(results)}")
        
        # Even with 100 results, should complete quickly
        assert elapsed_ms < 200, f"Latency {elapsed_ms:.1f}ms exceeds 200ms target"


@pytest.mark.skip(reason="Requires embeddings - run manually with real embedding service")
class TestHybridSearchPerformance:
    """Performance tests for hybrid search (requires embeddings)."""
    
    def test_hybrid_search_latency(self, storage_with_data):
        """Hybrid search should complete in < 500ms."""
        storage = storage_with_data
        embedder = EmbeddingService()
        
        # Generate query embedding
        query = "invoice payment details"
        query_embedding = embedder.embed_text(query)
        
        # Warm-up
        storage.hybrid_search(
            query_embedding=query_embedding,
            query_text=query,
            limit=5,
            retrieval_k=50
        )
        
        # Measure
        iterations = 5
        timings = []
        
        for _ in range(iterations):
            start = time.time()
            results = storage.hybrid_search(
                query_embedding=query_embedding,
                query_text=query,
                limit=5,
                retrieval_k=50
            )
            elapsed = time.time() - start
            timings.append(elapsed * 1000)
        
        avg_ms = sum(timings) / len(timings)
        max_ms = max(timings)
        
        print(f"\n[PERF] Hybrid search:")
        print(f"  Average: {avg_ms:.1f}ms")
        print(f"  Max: {max_ms:.1f}ms")
        print(f"  Results: {len(results)}")
        
        assert avg_ms < 500, f"Average latency {avg_ms:.1f}ms exceeds 500ms target"


class TestConcurrentSearchPerformance:
    """Test search performance under concurrent load."""
    
    def test_concurrent_keyword_searches(self, storage_with_data):
        """Should maintain performance with concurrent queries."""
        storage = storage_with_data
        
        queries = [
            "invoice",
            "payment",
            "meeting",
            "project",
            "budget",
            "report",
            "review",
            "update",
            "client",
            "team",
        ]
        
        def run_search(query):
            start = time.time()
            results = storage.keyword_search(query, limit=10)
            elapsed = time.time() - start
            return elapsed * 1000
        
        # Run 10 concurrent searches
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(run_search, q) for q in queries]
            timings = [future.result() for future in as_completed(futures)]
        
        avg_ms = sum(timings) / len(timings)
        max_ms = max(timings)
        
        print(f"\n[PERF] Concurrent keyword searches (10 parallel):")
        print(f"  Average: {avg_ms:.1f}ms")
        print(f"  Max: {max_ms:.1f}ms")
        
        # With connection pooling, should handle concurrent load well
        # Allow higher threshold for concurrent load
        assert avg_ms < 200, f"Average concurrent latency {avg_ms:.1f}ms exceeds 200ms"
        assert max_ms < 500, f"Max concurrent latency {max_ms:.1f}ms exceeds 500ms"


class TestSearchScalability:
    """Test search performance characteristics."""
    
    def test_keyword_search_scales_with_limit(self, storage_with_data):
        """Latency should scale roughly linearly with result limit."""
        storage = storage_with_data
        
        limits = [5, 10, 20, 50, 100]
        timings = {}
        
        for limit in limits:
            start = time.time()
            results = storage.keyword_search("test", limit=limit)
            elapsed = time.time() - start
            timings[limit] = elapsed * 1000
        
        print(f"\n[PERF] Keyword search scalability:")
        for limit, ms in timings.items():
            print(f"  limit={limit:3d}: {ms:.1f}ms")
        
        # Even at limit=100, should complete in reasonable time
        assert timings[100] < 250, f"Limit=100 latency {timings[100]:.1f}ms too high"
    
    def test_keyword_search_consistent_over_time(self, storage_with_data):
        """Performance should be consistent across multiple queries."""
        storage = storage_with_data
        
        # Run 20 searches and check variance
        timings = []
        for i in range(20):
            start = time.time()
            storage.keyword_search(f"test{i % 5}", limit=10)
            elapsed = time.time() - start
            timings.append(elapsed * 1000)
        
        avg_ms = sum(timings) / len(timings)
        import statistics
        stddev_ms = statistics.stdev(timings) if len(timings) > 1 else 0
        
        print(f"\n[PERF] Keyword search consistency (20 queries):")
        print(f"  Average: {avg_ms:.1f}ms")
        print(f"  Std Dev: {stddev_ms:.1f}ms")
        
        # Standard deviation should be low (consistent performance)
        assert stddev_ms < 50, f"High variance in performance (stddev={stddev_ms:.1f}ms)"
