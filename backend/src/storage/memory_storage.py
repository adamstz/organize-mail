"""In-memory storage backend for testing and development."""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone
import uuid

from ..models.message import MailMessage
from .storage_interface import StorageBackend


class InMemoryStorage(StorageBackend):
    """In-memory storage implementation for testing and development.
    
    This backend stores all data in memory dictionaries and will be lost
    when the process exits. Useful for tests and development.
    """
    
    def __init__(self):
        self._messages: dict[str, MailMessage] = {}
        self._meta: dict[str, str] = {}
        # store classification records in memory for tests/dev
        self._classifications: dict[str, list[dict]] = {}
        self._latest_classification: dict[str, str] = {}  # message_id -> classification_id

    def init_db(self) -> None:
        self._messages.clear()
        self._meta.clear()
        self._classifications.clear()
        self._latest_classification.clear()

    def save_message(self, msg: MailMessage) -> None:
        self._messages[msg.id] = msg

    def save_classification_record(self, record) -> None:
        lst = self._classifications.setdefault(record.message_id, [])
        lst.append(record.to_dict())
    
    def create_classification(self, message_id: str, labels: List[str], priority: str, summary: str, model: str = None) -> str:
        """Create a new classification record and link it to the message."""
        classification_id = str(uuid.uuid4())
        classification = {
            "id": classification_id,
            "message_id": message_id,
            "labels": labels,
            "priority": priority,
            "summary": summary,
            "model": model,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Store classification
        lst = self._classifications.setdefault(message_id, [])
        lst.append(classification)
        
        # Update message's latest classification reference
        self._latest_classification[message_id] = classification_id
        
        # Also update the message object if it exists
        if message_id in self._messages:
            msg = self._messages[message_id]
            msg.classification_labels = labels
            msg.priority = priority
            msg.summary = summary
        
        return classification_id
    
    def get_latest_classification(self, message_id: str) -> Optional[dict]:
        """Get the most recent classification for a message."""
        classification_id = self._latest_classification.get(message_id)
        if not classification_id:
            return None
        
        # Find the classification in the list
        for classification in self._classifications.get(message_id, []):
            if classification["id"] == classification_id:
                return classification
        
        return None

    def get_message_ids(self) -> List[str]:
        return list(self._messages.keys())
    
    def get_message_by_id(self, message_id: str) -> Optional[MailMessage]:
        """Get a single message by ID."""
        return self._messages.get(message_id)
    
    def get_unclassified_message_ids(self) -> List[str]:
        """Get IDs of messages that haven't been classified yet."""
        return [
            msg_id for msg_id in self._messages.keys()
            if msg_id not in self._latest_classification
        ]
    
    def count_classified_messages(self) -> int:
        """Count how many messages have been classified."""
        return len(self._latest_classification)

    def list_messages(self, limit: int = 100, offset: int = 0) -> List[MailMessage]:
        return list(self._messages.values())[offset:offset+limit]

    def get_history_id(self) -> Optional[str]:
        return self._meta.get("historyId")

    def set_history_id(self, history_id: str) -> None:
        self._meta["historyId"] = history_id

    def list_classification_records_for_message(self, message_id: str):
        data = self._classifications.get(message_id, [])
        from ..models.classification_record import ClassificationRecord
        out = []
        for d in data:
            out.append(ClassificationRecord.from_dict(d))
        return out
