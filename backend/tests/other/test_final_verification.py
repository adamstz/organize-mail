#!/usr/bin/env python3
"""Final verification test for complete chat history functionality."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from src.services.rag_engine import RAGQueryEngine
from src.services.llm_processor import LLMProcessor
from src.storage.memory_storage import InMemoryStorage
from src.services.embedding_service import EmbeddingService
from src.models.message import MailMessage
from unittest.mock import Mock, MagicMock

def test_complete_chat_history():
    """Test complete chat history functionality with corrected mappings."""
    print("🧪 Final Chat History Verification")
    print("=" * 50)
    
    # Set up environment for testing
    os.environ['LLM_PROVIDER'] = 'rules'
    
    try:
        # Create components
        storage = InMemoryStorage()
        llm = LLMProcessor()
        # Mock embedding service to avoid downloading models
        embedder = MagicMock(spec=EmbeddingService)
        embedder.embedding_dim = 384
        embedder.embed_text.return_value = [0.1] * 384
        embedder.embed_batch.return_value = [[0.1] * 384]
        rag_engine = RAGQueryEngine(storage, embedder, llm, top_k=5)
        
        print(f"✅ Components initialized with {llm.provider}/{llm.model}")
        
        # Add test data with different labels
        test_emails = [
            MailMessage(
                id="promo1",
                subject="Special Offer - 50% Off",
                snippet="Limited time offer on all items",
                from_="marketing@shop.com",
                internal_date=1704096000000,
                labels=["promotions"]
            ),
            MailMessage(
                id="job1",
                subject="Application Received",
                snippet="We received your job application",
                from_="hr@techcorp.com",
                internal_date=1704268800000,
                labels=["job-application"]
            ),
            MailMessage(
                id="receipt1",
                subject="Your Order Receipt",
                snippet="Thank you for your purchase",
                from_="orders@amazon.com",
                internal_date=1704441600000,
                labels=["receipts"]
            )
        ]
        
        for email in test_emails:
            storage.save_message(email)
        print(f"✅ Added {len(test_emails)} test emails to storage")
        
        # Test scenarios
        scenarios = [
            {
                "name": "Direct Promotional Query",
                "question": "how many promotional emails do I have?",
                "expected_type": "classification",
                "chat_history": []
            },
            {
                "name": "Follow-up Promotional Query", 
                "question": "who sent the most out of those?",
                "expected_type": "classification",
                "chat_history": [
                    {"role": "user", "content": "how many promotional emails do I have?"},
                    {"role": "assistant", "content": "You have promotional emails."}
                ]
            },
            {
                "name": "Direct Job Query",
                "question": "show me job applications",
                "expected_type": "classification", 
                "chat_history": []
            },
            {
                "name": "Follow-up Job Query",
                "question": "from those applications, any interviews?",
                "expected_type": "classification",
                "chat_history": [
                    {"role": "user", "content": "show me job applications"},
                    {"role": "assistant", "content": "Found job-related emails"}
                ]
            },
            {
                "name": "Topic Change Follow-up",
                "question": "what about receipts?",
                "expected_type": "classification",
                "chat_history": [
                    {"role": "user", "content": "how many promotions?"},
                    {"role": "assistant", "content": "Promotional emails found"},
                    {"role": "user", "content": "show me jobs"},
                    {"role": "assistant", "content": "Job emails found"}
                ]
            }
        ]
        
        print(f"\n📋 Testing {len(scenarios)} scenarios:")
        
        passed = 0
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n  📋 Scenario {i}: {scenario['name']}")
            print(f"     Question: {scenario['question']}")
            print(f"     History: {len(scenario['chat_history'])} messages")
            
            try:
                result = rag_engine.query(
                    question=scenario['question'],
                    chat_history=scenario['chat_history']
                )
                
                query_type = result.get('query_type')
                confidence = result.get('confidence')
                answer = result.get('answer', 'No answer')[:80] + '...'
                
                print(f"     Result Type: {query_type}")
                print(f"     Confidence: {confidence}")
                print(f"     Answer: {answer}")
                
                if query_type == scenario['expected_type']:
                    print(f"     ✅ PASS: Correct query type")
                    passed += 1
                else:
                    print(f"     ❌ FAIL: Expected {scenario['expected_type']}, got {query_type}")
                    
            except Exception as e:
                print(f"     ❌ ERROR: {e}")
        
        # Summary
        print(f"\n{'=' * 50}")
        print(f"📊 FINAL RESULTS")
        print(f"{'=' * 50}")
        print(f"Passed: {passed}/{len(scenarios)} scenarios ({passed/len(scenarios)*100:.1f}%)")
        
        if passed == len(scenarios):
            print("🎉 ALL SCENARIOS PASSED!")
            print("✅ Chat history functionality is working correctly")
            return True
        else:
            print(f"⚠️  {len(scenarios) - passed} scenarios failed")
            return False
            
    except Exception as e:
        print(f"❌ SETUP FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_complete_chat_history()
    sys.exit(0 if success else 1)
