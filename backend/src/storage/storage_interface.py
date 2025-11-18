from __future__ import annotations

from typing import List, Optional

from ..models.message import MailMessage


class StorageBackend:
    """Interface for storage backends."""

    def init_db(self) -> None:
        raise NotImplementedError()

    def save_message(self, msg: MailMessage) -> None:
        raise NotImplementedError()

    def get_message_ids(self) -> List[str]:
        """Return all message IDs."""
        raise NotImplementedError

    def get_message_by_id(self, message_id: str) -> Optional[MailMessage]:
        """Get a single message by ID."""
        raise NotImplementedError

    def get_unclassified_message_ids(self) -> List[str]:
        """Return IDs of messages that haven't been classified yet."""
        raise NotImplementedError

    def count_classified_messages(self) -> int:
        """Return count of messages that have been classified."""
        raise NotImplementedError

    def list_messages(self, limit: int = 100, offset: int = 0) -> List[MailMessage]:
        raise NotImplementedError()

    def get_history_id(self) -> Optional[str]:
        raise NotImplementedError()

    def set_history_id(self, history_id: str) -> None:
        raise NotImplementedError()

    # Classification record persistence
    def save_classification_record(self, record) -> None:
        """Persist a classification record object.

        `record` is expected to be an object with a `to_dict()` method.
        """
        raise NotImplementedError()

    def update_message_latest_classification(self, message_id: str, classification_id: str) -> None:
        """Update the latest_classification_id for a message."""
        raise NotImplementedError()

    def create_classification(self, message_id: str, labels: List[str], priority: str, summary: str, model: str = None) -> str:
        """Create a new classification and link it to a message.

        Returns the classification ID.
        """
        raise NotImplementedError()

    def get_latest_classification(self, message_id: str) -> Optional[dict]:
        """Get the most recent classification for a message.

        Returns dict with: id, labels, priority, summary, model, created_at
        """
        raise NotImplementedError()

    def list_classification_records_for_message(self, message_id: str):
        """Return a list of classification records for the given message id."""
        raise NotImplementedError()

    def get_label_counts(self) -> dict:
        """Get all unique classification labels with their counts."""
        raise NotImplementedError()

    # Optimized filtering methods (PostgreSQL only for now)
    def list_messages_by_label(self, label: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by classification label with database-level filtering.

        Returns tuple of (messages, total_count).
        """
        raise NotImplementedError()

    def list_messages_by_priority(self, priority: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List messages filtered by priority with database-level filtering.

        Returns tuple of (messages, total_count).
        """
        raise NotImplementedError()

    def list_classified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only classified messages with database-level filtering.

        Returns tuple of (messages, total_count).
        """
        raise NotImplementedError()

    def list_unclassified_messages(self, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
        """List only unclassified messages with database-level filtering.

        Returns tuple of (messages, total_count).
        """
        raise NotImplementedError()
