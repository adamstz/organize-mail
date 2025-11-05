#!/usr/bin/env python3
"""Dummy LLM script for testing the command-based LLM provider.

This script reads JSON from stdin and returns mock classification results.
Use this to test the command provider without needing a real LLM API.

Usage:
    export ORGANIZE_MAIL_LLM_CMD="python backend/examples/dummy_llm.py"
    export LLM_PROVIDER="command"
    python backend/examples/test_llm_providers.py
"""

import sys
import json


def main():
    # Read input from stdin
    input_data = json.load(sys.stdin)
    
    subject = input_data.get("subject", "").lower()
    body = input_data.get("body", "").lower()
    
    # Simple keyword-based mock classification
    labels = []
    priority = "normal"
    
    text = subject + " " + body
    
    if any(word in text for word in ["invoice", "payment", "bill", "receipt"]):
        labels.append("finance")
    if any(word in text for word in ["meeting", "schedule", "calendar"]):
        labels.append("meetings")
    if any(word in text for word in ["security", "password", "login", "alert"]):
        labels.append("security")
        priority = "high"
    if any(word in text for word in ["urgent", "asap", "immediately"]):
        priority = "high"
    if any(word in text for word in ["sale", "discount", "offer", "promotion"]):
        labels.append("promotions")
        priority = "low"
    
    # Return JSON result
    result = {
        "labels": labels,
        "priority": priority
    }
    
    print(json.dumps(result))


if __name__ == "__main__":
    main()
