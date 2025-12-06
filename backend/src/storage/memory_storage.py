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

    def update_message_latest_classification(self, message_id: str, classification_id: str) -> None:
        """Update the latest_classification_id for a message."""
        self._latest_classification[message_id] = classification_id

        # Also update the message object if it exists
        if message_id in self._messages:
            # Find the classification
            for classification in self._classifications.get(message_id, []):
                if classification["id"] == classification_id:
                    msg = self._messages[message_id]
                    msg.classification_labels = classification.get("labels")
                    msg.priority = classification.get("priority")
                    msg.summary = classification.get("summary")
                    break

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
        """Get a single message by ID with its latest classification."""
        msg = self._messages.get(message_id)
        if not msg:
            return None

        # Get latest classification if exists
        classification_id = self._latest_classification.get(message_id)
        if classification_id:
            for classification in self._classifications.get(message_id, []):
                if classification["id"] == classification_id:
                    # Create a copy with classification data
                    msg_copy = MailMessage(
                        id=msg.id,
                        thread_id=msg.thread_id,
                        from_=msg.from_,
                        to=msg.to,
                        subject=msg.subject,
                        snippet=msg.snippet,
                        labels=msg.labels,
                        internal_date=msg.internal_date,
                        payload=msg.payload,
                        raw=msg.raw,
                        headers=msg.headers,
                        classification_labels=classification.get("labels"),
                        priority=classification.get("priority"),
                        summary=classification.get("summary"),
                        has_attachments=msg.has_attachments
                    )
                    return msg_copy

        return msg

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
        return list(self._messages.values())[offset:offset + limit]

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

    def get_label_counts(self) -> dict:
        """Get all unique classification labels with their counts."""
        label_counts = {}
        for msg in self._messages.values():
            if msg.classification_labels:
                for label in msg.classification_labels:
                    label_counts[label] = label_counts.get(label, 0) + 1
        return label_counts

    def list_messages_by_label(self, label: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by classification label.

        Returns a tuple of (messages, total_count).
        """
        # Filter messages by label
        filtered = [
            msg for msg in self._messages.values()
            if msg.classification_labels and label in msg.classification_labels
        ]
        total = len(filtered)

        # Apply pagination
        paginated = filtered[offset:offset + limit]
        return paginated, total

    def list_messages_by_priority(self, priority: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by priority.

        Returns a tuple of (messages, total_count).
        """
        # Filter messages by priority (case-insensitive)
        filtered = [
            msg for msg in self._messages.values()
            if msg.priority and msg.priority.lower() == priority.lower()
        ]
        total = len(filtered)

        # Apply pagination
        paginated = filtered[offset:offset + limit]
        return paginated, total

    def list_classified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only classified messages.

        Returns a tuple of (messages, total_count).
        A message is classified if it has a latest_classification_id.
        """
        # Filter messages that are classified
        filtered = [
            msg for msg in self._messages.values()
            if msg.id in self._latest_classification
        ]
        total = len(filtered)

        # Apply pagination
        paginated = filtered[offset:offset + limit]
        return paginated, total

    def list_unclassified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only unclassified messages.

        Returns a tuple of (messages, total_count).
        A message is unclassified if it has no latest_classification_id.
        """
        # Filter messages that are not classified
        filtered = [
            msg for msg in self._messages.values()
            if msg.id not in self._latest_classification
        ]
        total = len(filtered)

        # Apply pagination
        paginated = filtered[offset:offset + limit]
        return paginated, total

    # RAG query support methods - stubs for testing
    def search_by_sender(self, sender: str, limit: int = 100) -> List[MailMessage]:
        """Search for messages from a specific sender."""
        sender_lower = sender.lower()
        filtered = [
            msg for msg in self._messages.values()
            if msg.from_ and sender_lower in msg.from_.lower()
        ]
        # Sort by internal_date descending (most recent first)
        filtered.sort(key=lambda m: m.internal_date or 0, reverse=True)
        return filtered[:limit]

    def search_by_attachment(self, limit: int = 100) -> List[MailMessage]:
        """Search for messages that have attachments."""
        filtered = [
            msg for msg in self._messages.values()
            if msg.has_attachments
        ]
        filtered.sort(key=lambda m: m.internal_date or 0, reverse=True)
        return filtered[:limit]

    def search_by_keywords(self, keywords: List[str], limit: int = 100) -> List[MailMessage]:
        """Search for messages matching any of the keywords."""
        if not keywords:
            return []

        def matches_any_keyword(msg: MailMessage) -> bool:
            text = f"{msg.subject or ''} {msg.from_ or ''} {msg.snippet or ''}".lower()
            return any(kw.lower() in text for kw in keywords)

        filtered = [msg for msg in self._messages.values() if matches_any_keyword(msg)]
        filtered.sort(key=lambda m: m.internal_date or 0, reverse=True)
        return filtered[:limit]

    def count_by_topic(self, topic: str) -> int:
        """Count messages matching a topic."""
        topic_lower = topic.lower()
        count = 0
        for msg in self._messages.values():
            text = f"{msg.subject or ''} {msg.from_ or ''} {msg.snippet or ''}".lower()
            if topic_lower in text:
                count += 1
        return count

    def get_daily_email_stats(self, days: int = 30) -> List[dict]:
        """Get email count statistics per day."""
        # Simple implementation - group by date
        from collections import defaultdict
        from datetime import datetime

        date_counts = defaultdict(int)
        for msg in self._messages.values():
            if msg.internal_date:
                dt = datetime.fromtimestamp(msg.internal_date / 1000)
                date_str = dt.strftime('%Y-%m-%d')
                date_counts[date_str] += 1

        # Sort by date descending and limit
        sorted_dates = sorted(date_counts.items(), reverse=True)[:days]
        return [{'date': d, 'count': c} for d, c in sorted_dates]

    def get_top_senders(self, limit: int = 10) -> List[dict]:
        """Get top email senders by message count."""
        from collections import Counter

        sender_counts = Counter(
            msg.from_ for msg in self._messages.values() if msg.from_
        )
        return [
            {'from_addr': addr, 'count': count}
            for addr, count in sender_counts.most_common(limit)
        ]

    def get_total_message_count(self) -> int:
        """Get total number of messages."""
        return len(self._messages)

    def get_unread_count(self) -> int:
        """Get count of unread messages."""
        count = 0
        for msg in self._messages.values():
            if msg.labels and 'UNREAD' in msg.labels:
                count += 1
        return count
