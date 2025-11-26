"""Test that classification fields (summary, priority, classification_labels) are stored and retrieved correctly."""

import tempfile
import os

from src.models.message import MailMessage
from src.storage.sqlite_storage import SQLiteStorage


def test_message_with_classification_fields():
    """Test that messages with classification data can be saved and retrieved using new API."""
    # Use a temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        storage = SQLiteStorage(db_path=db_path)
        storage.init_db()
        
        # Create a message (without classification data initially)
        msg = MailMessage(
            id="test-123",
            subject="URGENT: Invoice Payment Due",
            snippet="Please pay invoice by tomorrow",
            from_="billing@example.com",
        )
        
        # Save the message
        storage.save_message(msg)
        
        # Create classification using new API
        classification_id = storage.create_classification(
            message_id="test-123",
            labels=["finance", "urgent"],
            priority="high",
            summary="Payment reminder for outstanding invoice",
            model="test-model"
        )
        
        # Retrieve the message (should have classification via JOIN)
        retrieved = storage.get_message_by_id("test-123")
        
        # Verify classification fields were persisted
        assert retrieved.id == "test-123"
        assert retrieved.classification_labels == ["finance", "urgent"]
        assert retrieved.priority == "high"
        assert retrieved.summary == "Payment reminder for outstanding invoice"
        
    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_message_without_classification_fields():
    """Test that messages without classification data work correctly (backward compatibility)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        storage = SQLiteStorage(db_path=db_path)
        storage.init_db()
        
        # Create a message without classification data
        msg = MailMessage(
            id="test-456",
            subject="Regular Email",
            snippet="Just a normal email",
            from_="user@example.com",
        )
        
        # Save the message
        storage.save_message(msg)
        
        # Retrieve the message
        messages = storage.list_messages(limit=10)
        
        assert len(messages) == 1
        retrieved = messages[0]
        
        # Verify classification fields are None (not set)
        assert retrieved.id == "test-456"
        assert retrieved.classification_labels is None
        assert retrieved.priority is None
        assert retrieved.summary is None
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_update_message_with_classification():
    """Test that we can add classification data to an existing message using new API."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        storage = SQLiteStorage(db_path=db_path)
        storage.init_db()
        
        # Create and save a message without classification
        msg = MailMessage(
            id="test-789",
            subject="Email to classify",
            snippet="This needs classification",
            from_="sender@example.com",
        )
        storage.save_message(msg)
        
        # Verify no classification initially
        retrieved = storage.get_message_by_id("test-789")
        assert retrieved.classification_labels is None
        assert retrieved.priority is None
        assert retrieved.summary is None
        
        # Add classification using new API
        storage.create_classification(
            message_id="test-789",
            labels=["work", "important"],
            priority="normal",
            summary="Work-related email requiring attention",
            model="test-model"
        )
        
        # Retrieve and verify classification was added
        retrieved = storage.get_message_by_id("test-789")
        
        assert retrieved.classification_labels == ["work", "important"]
        assert retrieved.priority == "normal"
        assert retrieved.summary == "Work-related email requiring attention"
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
