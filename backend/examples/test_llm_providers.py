#!/usr/bin/env python3
"""Example script showing how to use different LLM providers for email classification.

Usage:
    # Test with OpenAI (requires OPENAI_API_KEY)
    export OPENAI_API_KEY="sk-..."
    export LLM_PROVIDER="openai"
    python examples/test_llm_providers.py

    # Test with Anthropic (requires ANTHROPIC_API_KEY)
    export ANTHROPIC_API_KEY="sk-ant-..."
    export LLM_PROVIDER="anthropic"
    python examples/test_llm_providers.py

    # Test with custom command
    export ORGANIZE_MAIL_LLM_CMD="python examples/dummy_llm.py"
    export LLM_PROVIDER="command"
    python examples/test_llm_providers.py

    # Test with rules (no API needed)
    export LLM_PROVIDER="rules"
    python examples/test_llm_providers.py
"""

import sys
import os

# Add parent to path for local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_processor import LLMProcessor


def main():
    # Example emails to classify
    test_cases = [
        {
            "subject": "URGENT: Invoice #12345 Payment Due",
            "body": "Your invoice for $5,000 is overdue. Please pay immediately to avoid late fees."
        },
        {
            "subject": "Security Alert: Unusual Login Detected",
            "body": "We noticed a login from an unrecognized device. Please verify your account."
        },
        {
            "subject": "Team Meeting Tomorrow at 3pm",
            "body": "Hi team, let's sync up tomorrow to discuss the project roadmap. Calendar invite attached."
        },
        {
            "subject": "Weekend Sale - 50% Off!",
            "body": "Don't miss our biggest sale of the year. Shop now and save big on all items."
        }
    ]

    processor = LLMProcessor()
    
    print(f"Using LLM Provider: {processor.provider}")
    print(f"Model: {processor.model or 'N/A'}")
    print("=" * 80)
    print()

    for i, case in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"  Subject: {case['subject']}")
        print(f"  Body: {case['body'][:60]}...")
        
        result = processor.categorize_message(case['subject'], case['body'])
        
        print(f"  Result:")
        print(f"    Labels: {result.get('labels', [])}")
        print(f"    Priority: {result.get('priority', 'normal')}")
        print()


if __name__ == "__main__":
    main()
