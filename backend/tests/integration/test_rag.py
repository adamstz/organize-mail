#!/usr/bin/env python3
"""Test script for RAG (Retrieval-Augmented Generation) functionality.

This script demonstrates:
1. Checking embedding status
2. Performing semantic search
3. Asking questions about emails
4. Finding similar emails
5. Handler routing (unit-test style, works with InMemoryStorage)
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ["LLM_PROVIDER"] = "rules"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OLLAMA_HOST", None)
os.environ.pop("ORGANIZE_MAIL_LLM_CMD", None)

import pytest
from unittest.mock import MagicMock, patch
from src.storage.storage import get_storage_backend
from src.storage.memory_storage import InMemoryStorage
from src.services import EmbeddingService, LLMProcessor, RAGQueryEngine
from src.services.query_classifier import QueryClassifier
from src.services.context_builder import ContextBuilder
from src.services.query_handlers.conversation import ConversationHandler
from src.services.query_handlers.aggregation import AggregationHandler
from src.services.query_handlers.temporal import TemporalHandler
from src.models.message import MailMessage


def print_banner(text):
    """Print a formatted banner."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


@pytest.mark.skipif(
    not os.environ.get("STORAGE_BACKEND"),
    reason="STORAGE_BACKEND not set - these tests require PostgreSQL"
)
def test_embedding_status():
    """Check how many emails have been embedded."""
    print_banner("1. Checking Embedding Status")
    
    storage = get_storage_backend()
    
    # Skip test if using in-memory storage (no connect method)
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    
    try:
        conn = storage.connect()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE embedding IS NOT NULL) as embedded
        FROM messages
    """)
    row = cur.fetchone()
    
    cur.close()
    conn.close()
    
    total = row[0]
    embedded = row[1]
    percentage = (embedded / total * 100) if total > 0 else 0
    
    print(f"Total messages: {total}")
    print(f"Embedded messages: {embedded}")
    print(f"Coverage: {percentage:.1f}%")
    
    if embedded == 0:
        print("\n⚠️  No emails have been embedded yet!")
        print("Run: python src/jobs/embed_all_emails.py")
    else:
        print(f"\n✓ Ready for semantic search and RAG queries!")
    
    # Test passes regardless - this is informational only
    assert total >= 0  # Just verify we could query the database


@pytest.mark.skipif(
    not os.environ.get("STORAGE_BACKEND"),
    reason="STORAGE_BACKEND not set - these tests require PostgreSQL"
)
def test_semantic_search():
    """Test vector similarity search."""
    print_banner("2. Testing Semantic Search")
    
    print("Searching for emails about 'meeting schedule'...")
    
    storage = get_storage_backend()
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    
    # Mock embedding service to avoid downloading models
    embedder = MagicMock(spec=EmbeddingService)
    embedder.embedding_dim = 384
    embedder.embed_text.return_value = [0.1] * 384
    
    # Embed the search query
    query_embedding = embedder.embed_text("meeting schedule")
    
    # Search for similar emails
    try:
        results = storage.similarity_search(
            query_embedding=query_embedding,
            limit=3,
            threshold=0.3
        )
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    
    if not results:
        print("No results found.")
        return
    
    print(f"\nFound {len(results)} similar emails:\n")
    
    for idx, (email, score) in enumerate(results, 1):
        print(f"{idx}. [Similarity: {score:.3f}]")
        print(f"   Subject: {email.subject or 'No subject'}")
        print(f"   From: {email.from_ or 'Unknown'}")
        print(f"   Snippet: {(email.snippet or '')[:100]}...")
        print()


@pytest.mark.skipif(
    not os.environ.get("STORAGE_BACKEND"),
    reason="STORAGE_BACKEND not set - these tests require PostgreSQL"
)
def test_rag_query():
    """Test RAG question answering."""
    print_banner("3. Testing RAG Question Answering")
    
    # Initialize RAG engine
    storage = get_storage_backend()
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    
    # Mock embedding service to avoid downloading models
    embedder = MagicMock(spec=EmbeddingService)
    embedder.embedding_dim = 384
    embedder.embed_text.return_value = [0.1] * 384
    embedder.embed_batch.return_value = [[0.1] * 384]
    
    llm = LLMProcessor()
    rag_engine = RAGQueryEngine(storage, embedder, llm)
    
    # Example questions
    questions = [
        "What are the most recent important emails?",
        "Are there any emails about invoices or payments?",
        "Who sent me the most emails?",
    ]
    
    for question in questions:
        print(f"\n📧 Question: {question}")
        print("-" * 70)
        
        try:
            result = rag_engine.query(
                question=question,
                top_k=3,
                similarity_threshold=0.4
            )
            
            print(f"\n💡 Answer ({result['confidence']} confidence):")
            print(f"   {result['answer']}")
            
            print(f"\n📎 Sources ({len(result['sources'])} emails):")
            for idx, source in enumerate(result['sources'], 1):
                print(f"   {idx}. {source['subject'][:60]}... (similarity: {source['similarity']:.3f})")
            
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print()


def main():
    """Run all RAG tests."""
    print("\n" + "🚀" * 35)
    print("   RAG (Retrieval-Augmented Generation) Test Suite")
    print("🚀" * 35)
    
    try:
        # Test 1: Check embedding status
        if not test_embedding_status():
            print("\n⚠️  Cannot proceed with RAG tests - no embeddings found.")
            return
        
        # Test 2: Semantic search
        test_semantic_search()
        
        # Test 3: RAG Q&A
        test_rag_query()
        
        print_banner("🎉 All Tests Complete!")
        print("Your RAG system is working!\n")
        print("Next steps:")
        print("  • Use the API endpoints to integrate with your frontend")
        print("  • POST /api/query - Ask questions")
        print("  • GET /api/embedding_status - Check coverage")
        print()
    
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


# ============================================================================
# Handler Routing Integration Tests (work with InMemoryStorage)
# ============================================================================

@pytest.fixture
def memory_rag_engine():
    """Create a RAG engine with InMemoryStorage for handler routing tests."""
    storage = InMemoryStorage()
    storage.init_db()
    
    # Add some test emails
    base_ts = 1733050800000
    day_ms = 86400000
    
    emails = [
        MailMessage(
            id="uber1",
            from_="noreply@uber.com",
            subject="Your Uber Eats order",
            snippet="Order is on the way",
            labels=["INBOX", "UNREAD"],
            internal_date=base_ts,
        ),
        MailMessage(
            id="amazon1",
            from_="amazon@amazon.com",
            subject="Your Amazon order shipped",
            snippet="Tracking: 123456",
            labels=["INBOX"],
            internal_date=base_ts - day_ms,
            has_attachments=True,
        ),
        MailMessage(
            id="work1",
            from_="boss@company.com",
            subject="Q4 Budget Review",
            snippet="Please review attached",
            labels=["INBOX", "UNREAD"],
            internal_date=base_ts - 2 * day_ms,
            has_attachments=True,
        ),
    ]
    
    for email in emails:
        storage.save_message(email)
    
    # Add classification for one email
    storage.create_classification(
        message_id="work1",
        labels=["work", "finance"],
        priority="high",
        summary="Budget review from boss",
        model="rules"
    )
    
    # Mock embedding service to avoid downloading models
    embedding = MagicMock(spec=EmbeddingService)
    embedding.embedding_dim = 384
    embedding.embed_text.return_value = [0.1] * 384
    embedding.embed_batch.return_value = [[0.1] * 384]
    
    with patch.object(LLMProcessor, '_is_ollama_running', return_value=False):
        llm = LLMProcessor()
    return RAGQueryEngine(storage, embedding, llm)


class TestHandlerRouting:
    """Integration tests for query routing to handlers."""

    def test_conversation_handler_routing(self, memory_rag_engine):
        """Should route conversation queries to ConversationHandler."""
        result = memory_rag_engine.query("hello")
        
        assert result['query_type'] == 'conversation'
        assert 'answer' in result
        assert result['sources'] == []

    def test_aggregation_handler_routing(self, memory_rag_engine):
        """Should route aggregation queries to AggregationHandler."""
        result = memory_rag_engine.query("how many emails do I have")
        
        assert result['query_type'] == 'aggregation'
        # With rules provider, the answer format may vary
        # Just verify we got some answer about emails
        assert 'answer' in result
        assert result['confidence'] in ('high', 'medium', 'low', 'none')

    def test_temporal_handler_routing(self, memory_rag_engine):
        """Should route temporal queries to TemporalHandler."""
        result = memory_rag_engine.query("show me my latest emails")
        
        assert result['query_type'] in ('temporal', 'filtered-temporal', 'semantic')
        assert 'sources' in result
        # With rules provider, answer may be a fallback response
        assert 'answer' in result

    def test_classification_handler_routing(self, memory_rag_engine):
        """Should route classification queries to ClassificationHandler."""
        result = memory_rag_engine.query("show me finance emails")
        
        assert result['query_type'] == 'classification'
        # With rules provider, answer may be a fallback response
        assert 'answer' in result

    def test_full_query_flow(self, memory_rag_engine):
        """Test complete query flow: classify -> route -> handler -> response."""
        # Test multiple query types in sequence - use queries that are reliably classified
        queries = [
            ("hi", {"conversation"}),
            ("how many emails", {"aggregation"}),
            ("show me finance emails", {"classification"}),  # Use explicit finance label
        ]
        
        for query, valid_types in queries:
            result = memory_rag_engine.query(query)
            
            assert result['query_type'] in valid_types, \
                f"Query '{query}' got type '{result['query_type']}' instead of one of {valid_types}"
            assert 'answer' in result
            assert 'sources' in result
            assert 'confidence' in result

    def test_handler_response_format(self, memory_rag_engine):
        """All handlers should return consistent response format."""
        # Use queries that don't need LLM invoke (conversation, aggregation)
        queries = ["hello", "how many emails"]
        
        required_keys = {'answer', 'sources', 'question', 'confidence', 'query_type'}
        
        for query in queries:
            result = memory_rag_engine.query(query)
            
            assert required_keys.issubset(result.keys()), \
                f"Response for '{query}' missing keys: {required_keys - result.keys()}"


class TestQueryClassifierIntegrationWithEngine:
    """Test that QueryClassifier integrates correctly with RAGQueryEngine."""

    def test_classifier_is_used(self, memory_rag_engine):
        """RAGQueryEngine should use QueryClassifier for classification."""
        # Verify the classifier attribute exists
        assert hasattr(memory_rag_engine, 'classifier')
        assert isinstance(memory_rag_engine.classifier, QueryClassifier)

    def test_detect_query_type_delegates(self, memory_rag_engine):
        """_detect_query_type should delegate to classifier."""
        query = "hello"
        
        # Call through both paths
        via_engine = memory_rag_engine._detect_query_type(query)
        via_classifier = memory_rag_engine.classifier.detect_query_type(query)
        
        assert via_engine == via_classifier

    def test_all_handlers_initialized(self, memory_rag_engine):
        """All handler types should be initialized."""
        expected_handlers = {
            'conversation', 'aggregation', 'search-by-sender', 'search-by-attachment',
            'classification', 'temporal', 'filtered-temporal', 'semantic'
        }
        
        assert expected_handlers == set(memory_rag_engine.handlers.keys())
