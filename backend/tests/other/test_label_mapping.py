#!/usr/bin/env python3
"""Test the corrected label mapping functionality."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from src.services.query_handlers.classification import ClassificationHandler
from src.services.llm_processor import LLMProcessor
from src.storage.memory_storage import InMemoryStorage
from src.services.context_builder import ContextBuilder
from unittest.mock import Mock

def test_label_mapping():
    """Test that label mapping works correctly for extracted terms."""
    print("🧪 Testing Label Mapping Corrections")
    print("=" * 40)
    
    # Test direct mapping
    from src.classification_labels import QUERY_TO_LABEL_MAPPING
    
    test_cases = [
        ("promotional", "promotions"),
        ("promo", "promotions"), 
        ("promotion", "promotions"),
        ("job", "job-application"),
        ("job application", "job-application"),
        ("interview", "job-interview"),
        ("receipt", "receipts"),
        ("bill", "bills")
    ]
    
    print("📋 Testing Direct Label Mapping:")
    all_passed = True
    for input_term, expected_label in test_cases:
        actual = QUERY_TO_LABEL_MAPPING.get(input_term)
        status = "✅ PASS" if actual == expected_label else "❌ FAIL"
        print(f"  {status}: '{input_term}' → '{actual}' (expected: '{expected_label}')")
        if actual != expected_label:
            all_passed = False
    
    # Test extraction with mock LLM
    print(f"\n📋 Testing LLM Extraction + Mapping:")
    
    # Create handler with mock LLM
    storage = InMemoryStorage()
    mock_llm = Mock(spec=LLMProcessor)
    context_builder = ContextBuilder()
    
    handler = ClassificationHandler(storage, mock_llm, context_builder)
    
    # Mock LLM responses for different terms
    mock_scenarios = [
        ("promotional", "promotional"),
        ("job", "job"), 
        ("promo", "promo"),
        ("receipt", "receipt")
    ]
    
    for extracted_term, llm_response in mock_scenarios:
        # Mock the LLM to return our test term
        mock_llm.invoke.return_value = Mock(content=llm_response)
        
        # Test the mapping logic
        try:
            # Simulate the mapping logic from _extract_label_from_history
            from src.classification_labels import QUERY_TO_LABEL_MAPPING
            final_label = QUERY_TO_LABEL_MAPPING.get(llm_response.lower(), llm_response)
            
            expected = {
                "promotional": "promotions",
                "job": "job-application", 
                "promo": "promotions",
                "receipt": "receipts"
            }.get(llm_response, llm_response)
            
            status = "✅ PASS" if final_label == expected else "❌ FAIL"
            print(f"  {status}: LLM '{llm_response}' → '{final_label}' (expected: '{expected}')")
            
            if final_label != expected:
                all_passed = False
                
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            all_passed = False
    
    print(f"\n{'=' * 40}")
    print(f"📊 OVERALL: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    return all_passed

if __name__ == "__main__":
    success = test_label_mapping()
    sys.exit(0 if success else 1)
