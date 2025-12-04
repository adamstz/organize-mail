"""
Root-level test configuration for pytest.

This conftest.py provides fixtures and configuration that apply to ALL tests
in the test suite. It primarily handles:
- Setting LLM_PROVIDER=rules environment variable for deterministic testing
- Ensuring environment is consistent across all test modules

Note: pytest requires the filename 'conftest.py' for automatic fixture discovery.
"""
import os
import pytest


@pytest.fixture(autouse=True)
def reset_llm_provider_env():
    """
    Ensure LLM_PROVIDER is set to 'rules' for all tests.
    
    This fixture runs automatically before every test (autouse=True) and ensures
    that tests use the deterministic 'rules' provider instead of making actual
    LLM API calls.
    
    The fixture:
    1. Saves the original LLM_PROVIDER value
    2. Sets LLM_PROVIDER to 'rules' before each test
    3. Restores the original value after each test (cleanup)
    """
    original = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "rules"
    yield
    # Restore original value after test
    if original is None:
        os.environ.pop("LLM_PROVIDER", None)
    else:
        os.environ["LLM_PROVIDER"] = original
