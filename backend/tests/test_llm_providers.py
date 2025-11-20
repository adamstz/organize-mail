#!/usr/bin/env python3
"""Test different LLM providers quickly.

This file provides a lightweight harness to verify configuration and
connectivity for supported providers (Ollama, OpenAI, Anthropic).
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm_provider import get_llm_provider


def simple_prompt(provider_name: str, prompt: str = "Say hello"):
    print(f"\nTesting provider: {provider_name}")
    try:
        provider = get_llm_provider(provider_name)
        response = provider.completion(prompt)
        print("Response:")
        print(response[:1000])
    except Exception as e:
        print(f"Error testing {provider_name}: {e}")


def main():
    providers = ["ollama", "openai", "anthropic"]
    for p in providers:
        simple_prompt(p, prompt="Hello from the test harness. What is your name?")


if __name__ == "__main__":
    main()
