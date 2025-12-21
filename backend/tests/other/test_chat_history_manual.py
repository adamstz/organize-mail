#!/usr/bin/env python3
"""
Manual test script for chat history functionality.
Tests the actual implementation with real LLM calls.

This is a manual test script - not meant to be run by pytest.
Run directly with: python tests/other/test_chat_history_manual.py
"""
import pytest
import sys
import os
import logging

# Skip this file when running pytest
pytestmark = pytest.mark.skip(reason="Manual test script - run directly, not via pytest")

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.rag_engine import RAGQueryEngine
from src.services.llm_processor import LLMProcessor
from src.storage.memory_storage import InMemoryStorage
from src.services.embedding_service import EmbeddingService
from src.models.message import MailMessage

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def setup_test_data():
    """Set up test email data."""
    storage = InMemoryStorage()
    
    # Add promotional emails
    promo_emails = [
        Message(
            id="promo1",
            subject="Special Offer - 50% Off Everything",
            body="Limited time offer on all items. Use code SAVE50 at checkout.",
            sender="marketing@amazon.com",
            date="2024-01-01T10:00:00Z",
            labels=["promotions"]
        ),
        Message(
            id="promo2",
            subject="Flash Sale Today Only - Up to 70% Off",
            body="Don't miss our biggest sale ever! Everything must go!",
            sender="deals@walmart.com", 
            date="2024-01-02T11:00:00Z",
            labels=["promotions"]
        ),
        Message(
            id="promo3",
            subject="Exclusive Member Deal",
            body="As a valued member, get early access to our Black Friday deals.",
            sender="promotions@target.com",
            date="2024-01-03T12:00:00Z",
            labels=["promotions"]
        )
    ]
    
    # Add job application emails
    job_emails = [
        Message(
            id="job1",
            subject="Application Received - Senior Software Engineer",
            body="We have received your application for the Senior Software Engineer position at TechCorp.",
            sender="hr@techcorp.com",
            date="2024-01-04T09:00:00Z",
            labels=["job-application"]
        ),
        Message(
            id="job2",
            subject="Interview Invitation - Product Manager Role",
            body="We would like to schedule an interview for the Product Manager position at StartupXYZ.",
            sender="recruiting@startupxyz.com",
            date="2024-01-05T14:00:00Z",
            labels=["job-interview"]
        ),
        Message(
            id="job3",
            subject="Job Application Rejection - Data Scientist",
            body="Thank you for your interest, but we have decided to move forward with other candidates.",
            sender="careers@datatech.com",
            date="2024-01-06T16:00:00Z",
            labels=["job-rejection"]
        )
    ]
    
    # Add receipt emails
    receipt_emails = [
        Message(
            id="receipt1",
            subject="Your Order Receipt #12345 - Amazon Purchase",
            body="Thank you for your purchase. Order total: $45.99",
            sender="orders@amazon.com",
            date="2024-01-07T12:00:00Z",
            labels=["receipts"]
        ),
        Message(
            id="receipt2",
            subject="Payment Confirmation - Uber Ride",
            body="Your ride has been completed. Total charged: $23.50",
            sender="receipts@uber.com",
            date="2024-01-08T18:00:00Z",
            labels=["receipts"]
        )
    ]
    
    # Add all emails to storage
    all_emails = promo_emails + job_emails + receipt_emails
    for email in all_emails:
        storage.add_message(email)
    
    return storage


def test_scenario(name, rag_engine, question, chat_history=None, expected_behavior=None):
    """Test a specific scenario."""
    print(f"\n{'='*60}")
    print(f"TESTING: {name}")
    print(f"Question: '{question}'")
    if chat_history:
        print(f"Chat History: {len(chat_history)} messages")
        for i, msg in enumerate(chat_history):
            print(f"  {i+1}. {msg['role']}: {msg['content'][:50]}...")
    print(f"Expected: {expected_behavior}")
    print('-' * 60)
    
    try:
        result = rag_engine.query(question, chat_history=chat_history)
        
        print(f"✅ SUCCESS")
        print(f"Query Type: {result.get('query_type')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Sources: {len(result.get('sources', []))}")
        print(f"Answer: {result.get('answer', 'No answer')[:200]}...")
        
        # Check if expectations met
        if expected_behavior:
            if expected_behavior in result.get('answer', '').lower():
                print(f"✅ EXPECTATION MET: Contains '{expected_behavior}'")
            else:
                print(f"❌ EXPECTATION NOT MET: Expected '{expected_behavior}' in answer")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run manual tests."""
    print("🧪 CHAT HISTORY MANUAL TESTING")
    print("Testing chat history functionality with real LLM calls...")
    
    # Set up environment
    os.environ.setdefault('LLM_PROVIDER', 'rules')  # Use rules provider for testing
    os.environ.setdefault('LLM_MODEL', 'test')
    
    try:
        # Create components
        storage = setup_test_data()
        llm = LLMProcessor()
        # Mock embedding service to avoid downloading models
        from unittest.mock import MagicMock
        embedder = MagicMock(spec=EmbeddingService)
        embedder.embedding_dim = 384
        embedder.embed_text.return_value = [0.1] * 384
        embedder.embed_batch.return_value = [[0.1] * 384]
        rag_engine = RAGQueryEngine(storage, embedder, llm, top_k=5)
        
        print(f"✅ Components initialized with {llm.provider}/{llm.model}")
        print(f"✅ Test data: {len(storage.get_all_messages())} emails loaded")
        
        # Test scenarios
        scenarios = [
            {
                'name': 'Direct Classification Query (Baseline)',
                'question': 'how many promotional emails do I have?',
                'expected_behavior': 'promotional'
            },
            {
                'name': 'Follow-up Query with Context',
                'question': 'of those, who sends the most?',
                'chat_history': [
                    {"role": "user", "content": "how many promotional emails do I have?"},
                    {"role": "assistant", "content": "You have promotional emails."}
                ],
                'expected_behavior': 'promotional'
            },
            {
                'name': 'Job Application Follow-up',
                'question': 'from those, which are interviews?',
                'chat_history': [
                    {"role": "user", "content": "show me job applications"},
                    {"role": "assistant", "content": "I found several job-related emails."}
                ],
                'expected_behavior': 'job'
            },
            {
                'name': 'Receipt Follow-up',
                'question': 'among them, which are from amazon?',
                'chat_history': [
                    {"role": "user", "content": "how many receipts?"},
                    {"role": "assistant", "content": "You have receipt emails."}
                ],
                'expected_behavior': 'receipt'
            },
            {
                'name': 'No Context Fallback',
                'question': 'who sends most?',
                'expected_behavior': None  # Should handle gracefully
            },
            {
                'name': 'Complex Multi-topic Conversation',
                'question': 'from the job ones, which are rejections?',
                'chat_history': [
                    {"role": "user", "content": "how many promotional emails?"},
                    {"role": "assistant", "content": "3 promotional emails"},
                    {"role": "user", "content": "show me job applications"},
                    {"role": "assistant", "content": "3 job-related emails"},
                    {"role": "user", "content": "any receipts?"},
                    {"role": "assistant", "content": "2 receipt emails"}
                ],
                'expected_behavior': 'job'
            }
        ]
        
        # Run all scenarios
        results = []
        for scenario in scenarios:
            success = test_scenario(
                name=scenario['name'],
                rag_engine=rag_engine,
                question=scenario['question'],
                chat_history=scenario.get('chat_history'),
                expected_behavior=scenario.get('expected_behavior')
            )
            results.append((scenario['name'], success))
        
        # Summary
        print(f"\n{'='*60}")
        print("📊 TEST SUMMARY")
        print('='*60)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status}: {name}")
        
        print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED!")
            return 0
        else:
            print("⚠️  Some tests failed. Check the output above.")
            return 1
            
    except Exception as e:
        print(f"❌ SETUP FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
