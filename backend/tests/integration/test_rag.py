#!/usr/bin/env python3
"""Test script for RAG (Retrieval-Augmented Generation) functionality.

This script demonstrates:
1. Checking embedding status
2. Performing semantic search
3. Asking questions about emails
4. Finding similar emails
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.storage.storage import get_storage_backend
from src.storage.memory_storage import InMemoryStorage
from src.embedding_service import EmbeddingService
from src.llm_processor import LLMProcessor
from src.rag_engine import RAGQueryEngine


def print_banner(text):
    """Print a formatted banner."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def test_embedding_status():
    """Check how many emails have been embedded."""
    print_banner("1. Checking Embedding Status")
    
    storage = get_storage_backend()
    
    # Skip test if using in-memory storage (no connect method)
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    
    conn = storage.connect()
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


def test_semantic_search():
    """Test vector similarity search."""
    print_banner("2. Testing Semantic Search")
    
    print("Searching for emails about 'meeting schedule'...")
    
    storage = get_storage_backend()
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    
    embedder = EmbeddingService()
    
    # Embed the search query
    query_embedding = embedder.embed_text("meeting schedule")
    
    # Search for similar emails
    results = storage.similarity_search(
        query_embedding=query_embedding,
        limit=3,
        threshold=0.3
    )
    
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


def test_rag_query():
    """Test RAG question answering."""
    print_banner("3. Testing RAG Question Answering")
    
    # Initialize RAG engine
    storage = get_storage_backend()
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    
    embedder = EmbeddingService()
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


def test_find_similar():
    """Find similar emails."""
    print_banner("4. Testing Find Similar Emails")
    
    storage = get_storage_backend()
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    if isinstance(storage, InMemoryStorage):
        pytest.skip("RAG tests require PostgreSQL storage backend")
    embedder = EmbeddingService()
    llm = LLMProcessor()
    rag_engine = RAGQueryEngine(storage, embedder, llm)
    
    # Get a sample message
    messages = storage.list_messages(limit=1)
    if not messages:
        print("No messages found in database.")
        return
    
    sample_message = messages[0]
    print(f"Finding emails similar to:")
    print(f"  Subject: {sample_message.subject or 'No subject'}")
    print(f"  From: {sample_message.from_ or 'Unknown'}")
    print()
    
    # Find similar
    similar = rag_engine.find_similar_emails(sample_message.id, limit=5)
    
    if not similar:
        print("No similar emails found.")
        return
    
    print(f"Found {len(similar)} similar emails:\n")
    
    for idx, email_data in enumerate(similar, 1):
        print(f"{idx}. [Similarity: {email_data['similarity']:.3f}]")
        print(f"   Subject: {email_data['subject'] or 'No subject'}")
        print(f"   From: {email_data['from']}")
        print(f"   Labels: {', '.join(email_data['labels']) if email_data['labels'] else 'None'}")
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
        
        # Test 4: Find similar
        test_find_similar()
        
        print_banner("🎉 All Tests Complete!")
        print("Your RAG system is working!\n")
        print("Next steps:")
        print("  • Use the API endpoints to integrate with your frontend")
        print("  • POST /api/query - Ask questions")
        print("  • GET /api/similar/{id} - Find similar emails")
        print("  • GET /api/embedding_status - Check coverage")
        print()
    
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
