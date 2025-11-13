"""Smoke tests - verify critical functionality works.

These are minimal, fast tests that catch catastrophic failures.
Run these after deployment or as a quick sanity check.
"""

import pytest
from fastapi.testclient import TestClient


def test_can_import_api():
    """Verify API module imports without crashing."""
    from src import api
    assert api.app is not None


def test_can_import_core_modules():
    """Verify all critical modules can be imported."""
    from src.llm_processor import LLMProcessor
    from src.storage import storage
    from src.models.message import MailMessage
    from src.models.classification_record import ClassificationRecord
    # If we get here, imports worked


def test_api_starts():
    """Verify API can start and respond to requests."""
    from src.api import app
    from src.storage import storage
    
    # Initialize database first
    storage.init_db()
    
    client = TestClient(app)
    response = client.get("/messages")
    assert response.status_code == 200


def test_llm_processor_works():
    """Verify LLM processor can classify (using fallback)."""
    import os
    from src.llm_processor import LLMProcessor
    
    os.environ["LLM_PROVIDER"] = "rules"
    processor = LLMProcessor()
    result = processor.categorize_message(
        "Invoice Payment",
        "Please pay $100"
    )
    
    assert isinstance(result, dict)
    assert "labels" in result
    assert "priority" in result
    assert "summary" in result
    assert isinstance(result["labels"], list)
    assert result["priority"] in ["high", "normal", "low"]
    assert isinstance(result["summary"], str)


def test_storage_works():
    """Verify storage can save messages."""
    from src.storage import storage
    from src.models.message import MailMessage
    
    # Initialize database first
    storage.init_db()
    
    msg = MailMessage(
        id="smoke-test-msg",
        subject="Smoke Test",
        snippet="Testing storage",
        from_="test@example.com",
    )
    
    # Just verify save doesn't crash
    storage.save_message(msg)
    
    # Verify we can list message IDs
    msg_ids = storage.get_message_ids()
    assert isinstance(msg_ids, list)


def test_classification_record_roundtrip():
    """Verify classification records work end-to-end."""
    from src.models.classification_record import ClassificationRecord
    from datetime import datetime
    
    record = ClassificationRecord(
        id="smoke-test-cls",
        message_id="smoke-test-msg",
        labels=["test"],
        priority="normal",
        model="test-model",
        created_at=datetime.now()
    )
    
    # Verify serialization works
    data = record.to_dict()
    restored = ClassificationRecord.from_dict(data)
    assert restored.id == record.id
    assert restored.labels == record.labels
