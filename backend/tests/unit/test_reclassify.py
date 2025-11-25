"""Tests for the reclassify endpoint and update_message_latest_classification functionality."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.models.message import MailMessage
from src.models.classification_record import ClassificationRecord
from src.storage.memory_storage import InMemoryStorage


class TestUpdateMessageLatestClassification:
    """Tests for update_message_latest_classification method."""
    
    def test_update_message_latest_classification(self):
        """Test that update_message_latest_classification updates the message."""
        storage = InMemoryStorage()
        storage.init_db()
        
        # Create a test message
        msg = MailMessage(
            id="test-msg-1",
            thread_id="thread-1",
            from_="sender@example.com",
            to="recipient@example.com",
            subject="Test Subject",
            snippet="Test snippet",
            labels=["INBOX"],
            internal_date=1234567890,
            payload={},
            raw=None,
            headers={},
            has_attachments=False
        )
        storage.save_message(msg)
        
        # Create first classification
        classification1 = ClassificationRecord(
            id="class-1",
            message_id="test-msg-1",
            labels=["job-application"],
            priority="high",
            summary="First summary",
            model="gemma:2b",
            created_at=datetime.now(timezone.utc)
        )
        storage.save_classification_record(classification1)
        storage.update_message_latest_classification("test-msg-1", "class-1")
        
        # Verify first classification is linked
        retrieved = storage.get_message_by_id("test-msg-1")
        assert retrieved.classification_labels == ["job-application"]
        assert retrieved.priority == "high"
        assert retrieved.summary == "First summary"
        
        # Create second classification (reclassify)
        classification2 = ClassificationRecord(
            id="class-2",
            message_id="test-msg-1",
            labels=["job-rejection"],
            priority="normal",
            summary="Updated summary",
            model="gemma:7b",
            created_at=datetime.now(timezone.utc)
        )
        storage.save_classification_record(classification2)
        storage.update_message_latest_classification("test-msg-1", "class-2")
        
        # Verify second classification is now linked
        retrieved = storage.get_message_by_id("test-msg-1")
        assert retrieved.classification_labels == ["job-rejection"]
        assert retrieved.priority == "normal"
        assert retrieved.summary == "Updated summary"
        
        # Verify both classifications exist in history
        history = storage.list_classification_records_for_message("test-msg-1")
        assert len(history) == 2
        assert history[0].id in ["class-1", "class-2"]
        assert history[1].id in ["class-1", "class-2"]


class TestReclassifyEndpoint:
    """Tests for the /messages/{message_id}/reclassify API endpoint."""
    
    @pytest.fixture
    def mock_storage(self):
        """Create a mock storage backend."""
        storage = InMemoryStorage()
        storage.init_db()
        return storage
    
    @pytest.fixture
    def test_message(self, mock_storage):
        """Create a test message with Gmail payload structure."""
        msg = MailMessage(
            id="test-msg-123",
            thread_id="thread-123",
            from_="recruiter@company.com",
            to="candidate@example.com",
            subject="Job Application Update",
            snippet="We would like to invite you...",
            labels=["INBOX"],
            internal_date=1234567890,
            payload={
                "mimeType": "text/plain",
                "body": {
                    "data": "V2Ugd291bGQgbGlrZSB0byBpbnZpdGUgeW91IHRvIGFuIGludGVydmlldyE="  # Base64: "We would like to invite you to an interview!"
                }
            },
            raw=None,
            headers={"Subject": "Job Application Update", "From": "recruiter@company.com"},
            has_attachments=False
        )
        mock_storage.save_message(msg)
        return msg
    
    def test_reclassify_creates_new_classification(self, mock_storage, test_message):
        """Test that reclassify creates a new classification record."""
        from src.api import app
        from fastapi.testclient import TestClient
        from src import storage as storage_module
        
        # Set the storage backend to our mock before the API uses it
        storage_module.set_storage_backend(mock_storage)
        
        try:
            # Mock LLM processor
            mock_processor = MagicMock()
            mock_processor.categorize_message.return_value = {
                "labels": ["job-interview"],
                "priority": "high",
                "summary": "Interview invitation from company"
            }
            mock_processor.model = "gemma:7b"
            
            with patch('src.api.LLMProcessor', return_value=mock_processor):
                client = TestClient(app)
                
                # Make reclassify request
                response = client.post(
                    f"/messages/{test_message.id}/reclassify",
                    json={"model": "gemma:7b"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["message_id"] == test_message.id
                
                # Verify new classification was created
                history = mock_storage.list_classification_records_for_message(test_message.id)
                assert len(history) == 1
                assert history[0].labels == ["job-interview"]
                assert history[0].priority == "high"
                assert history[0].summary == "Interview invitation from company"
        finally:
            # Reset storage backend
            storage_module._backend = None
    
    def test_reclassify_updates_message_latest_classification(self, mock_storage, test_message):
        """Test that reclassify updates the message's latest_classification_id."""
        from src.api import app
        from fastapi.testclient import TestClient
        from src import storage as storage_module
        
        # Create initial classification
        initial_classification = ClassificationRecord(
            id="initial-class",
            message_id=test_message.id,
            labels=["job-application"],
            priority="normal",
            summary="Initial classification",
            model="gemma:2b",
            created_at=datetime.now(timezone.utc)
        )
        mock_storage.save_classification_record(initial_classification)
        mock_storage.update_message_latest_classification(test_message.id, "initial-class")
        
        # Verify initial state
        retrieved = mock_storage.get_message_by_id(test_message.id)
        assert retrieved.classification_labels == ["job-application"]
        assert retrieved.priority == "normal"
        
        # Set the storage backend to our mock
        storage_module.set_storage_backend(mock_storage)
        
        try:
            # Mock LLM processor
            mock_processor = MagicMock()
            mock_processor.categorize_message.return_value = {
                "labels": ["job-rejection"],
                "priority": "low",
                "summary": "Rejection email"
            }
            mock_processor.model = "gemma:7b"
            
            with patch('src.api.LLMProcessor', return_value=mock_processor):
                client = TestClient(app)
                
                # Make reclassify request
                response = client.post(
                    f"/messages/{test_message.id}/reclassify",
                    json={"model": "gemma:7b"}
                )
                
                assert response.status_code == 200
                
                # Verify message now has updated classification
                retrieved = mock_storage.get_message_by_id(test_message.id)
                assert retrieved.classification_labels == ["job-rejection"]
                assert retrieved.priority == "low"
                assert retrieved.summary == "Rejection email"
                
                # Verify both classifications exist in history
                history = mock_storage.list_classification_records_for_message(test_message.id)
                assert len(history) == 2
        finally:
            storage_module._backend = None
    
    def test_reclassify_extracts_full_body(self, mock_storage):
        """Test that reclassify extracts the full body from Gmail payload."""
        from src.api import app
        from fastapi.testclient import TestClient
        from src import storage as storage_module
        
        # Create message with multipart payload
        msg = MailMessage(
            id="test-multipart",
            thread_id="thread-mp",
            from_="sender@example.com",
            to="recipient@example.com",
            subject="Multipart Message",
            snippet="Short snippet...",
            labels=["INBOX"],
            internal_date=1234567890,
            payload={
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {
                            "data": "VGhpcyBpcyB0aGUgZnVsbCBib2R5IG9mIHRoZSBlbWFpbCB3aXRoIG11Y2ggbW9yZSBjb250ZW50IHRoYW4gdGhlIHNuaXBwZXQu"  # "This is the full body of the email with much more content than the snippet."
                        }
                    }
                ]
            },
            raw=None,
            headers={},
            has_attachments=False
        )
        mock_storage.save_message(msg)
        
        storage_module.set_storage_backend(mock_storage)
        
        try:
            # Mock LLM processor and capture what body it receives
            mock_processor = MagicMock()
            mock_processor.categorize_message.return_value = {
                "labels": ["personal"],
                "priority": "normal",
                "summary": "Personal email"
            }
            mock_processor.model = "gemma:2b"
            
            with patch('src.api.LLMProcessor', return_value=mock_processor):
                client = TestClient(app)
                
                response = client.post(
                    f"/messages/{msg.id}/reclassify",
                    json={"model": "gemma:2b"}
                )
                
                assert response.status_code == 200
                
                # Verify LLM was called with full body, not snippet
                mock_processor.categorize_message.assert_called_once()
                call_args = mock_processor.categorize_message.call_args
                subject, body = call_args[0]
                
                assert subject == "Multipart Message"
                assert "full body" in body
                assert len(body) > len(msg.snippet)
        finally:
            storage_module._backend = None
    
    def test_reclassify_with_different_models(self, mock_storage, test_message):
        """Test that reclassify respects the model parameter."""
        from src.api import app
        from fastapi.testclient import TestClient
        from src import storage as storage_module
        
        storage_module.set_storage_backend(mock_storage)
        
        try:
            mock_processor = MagicMock()
            mock_processor.categorize_message.return_value = {
                "labels": ["test"],
                "priority": "normal",
                "summary": "Test"
            }
            
            with patch('src.api.LLMProcessor', return_value=mock_processor):
                client = TestClient(app)
                
                # Reclassify with gemma:7b
                response = client.post(
                    f"/messages/{test_message.id}/reclassify",
                    json={"model": "gemma:7b"}
                )
                
                assert response.status_code == 200
                
                # Verify classification record has correct model
                history = mock_storage.list_classification_records_for_message(test_message.id)
                assert len(history) == 1
                assert history[0].model == "gemma:7b"
        finally:
            storage_module._backend = None


class TestGetModelsEndpoint:
    """Tests for the /models endpoint."""
    
    def test_get_models_returns_available_models(self):
        """Test that /models endpoint returns list of available Ollama models."""
        from src.api import app
        from fastapi.testclient import TestClient
        import json
        from io import BytesIO
        
        # Mock the urllib.request.urlopen response
        mock_response = MagicMock()
        mock_data = json.dumps({
            "models": [
                {"name": "gemma:2b", "size": 123456},
                {"name": "gemma:7b", "size": 789012},
                {"name": "llama2:13b", "size": 345678}
            ]
        }).encode('utf-8')
        mock_response.read.return_value = mock_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            client = TestClient(app)
            response = client.get("/models")
            
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert len(data["models"]) == 3
            assert data["models"][0]["name"] == "gemma:2b"
            assert data["models"][1]["name"] == "gemma:7b"
            assert data["models"][2]["name"] == "llama2:13b"
    
    def test_get_models_handles_ollama_unavailable(self):
        """Test that /models endpoint handles Ollama being unavailable."""
        from src.api import app
        from fastapi.testclient import TestClient
        
        # Mock connection error
        with patch('urllib.request.urlopen', side_effect=Exception("Connection refused")):
            client = TestClient(app)
            response = client.get("/models")
            
            # The endpoint catches exceptions and returns 200 with empty models and error
            assert response.status_code == 200
            data = response.json()
            assert "models" in data
            assert len(data["models"]) == 0
            assert "error" in data
