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

    # RAG query support methods
    def search_by_sender(self, sender: str, limit: int = 100) -> List[MailMessage]:
        """Search for messages from a specific sender.

        Args:
            sender: Sender name or email (partial match with ILIKE)
            limit: Maximum number of results

        Returns:
            List of matching messages, sorted by date descending.
        """
        raise NotImplementedError()

    def search_by_attachment(self, limit: int = 100) -> List[MailMessage]:
        """Search for messages that have attachments.

        Args:
            limit: Maximum number of results

        Returns:
            List of messages with attachments, sorted by date descending.
        """
        raise NotImplementedError()

    def search_by_keywords(self, keywords: List[str], limit: int = 100) -> List[MailMessage]:
        """Search for messages matching any of the keywords.

        Args:
            keywords: List of keywords to search for in subject, from_addr, or snippet
            limit: Maximum number of results

        Returns:
            List of matching messages, sorted by date descending.
        """
        raise NotImplementedError()

    def count_by_topic(self, topic: str) -> int:
        """Count messages matching a topic in subject, from_addr, or snippet.

        Args:
            topic: Topic string to search for (partial match)

        Returns:
            Count of matching messages.
        """
        raise NotImplementedError()

    def get_daily_email_stats(self, days: int = 30) -> List[dict]:
        """Get email count statistics per day.

        Args:
            days: Number of days to look back

        Returns:
            List of dicts with 'date' and 'count' keys.
        """
        raise NotImplementedError()

    def get_top_senders(self, limit: int = 10) -> List[dict]:
        """Get top email senders by message count.

        Args:
            limit: Number of top senders to return

        Returns:
            List of dicts with 'from_addr' and 'count' keys.
        """
        raise NotImplementedError()

    def get_total_message_count(self) -> int:
        """Get total number of messages in the database.

        Returns:
            Total message count.
        """
        raise NotImplementedError()

    def get_unread_count(self) -> int:
        """Get count of unread messages.

        Returns:
            Count of messages with UNREAD label.
        """
        raise NotImplementedError()

    # Chat session management methods
    def create_chat_session(self, title: Optional[str] = None) -> str:
        """Create a new chat session.

        Args:
            title: Optional session title

        Returns:
            Chat session ID (UUID)
        """
        raise NotImplementedError()

    def list_chat_sessions(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """List all chat sessions.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of dicts with id, title, created_at, updated_at, message_count
        """
        raise NotImplementedError()

    def get_chat_session_messages(self, chat_session_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
        """Get all messages for a chat session.

        Args:
            chat_session_id: Chat session ID
            limit: Maximum number of messages to return
            offset: Number of messages to skip

        Returns:
            List of dicts with id, role, content, sources, confidence, query_type, timestamp
        """
        raise NotImplementedError()

    def save_message_to_chat_session(
        self,
        chat_session_id: str,
        role: str,
        content: str,
        sources: Optional[List[dict]] = None,
        confidence: Optional[str] = None,
        query_type: Optional[str] = None
    ) -> str:
        """Save a message to a chat session.

        Args:
            chat_session_id: Chat session ID
            role: Message role ('user' or 'assistant')
            content: Message content
            sources: Optional list of source email metadata
            confidence: Optional confidence level
            query_type: Optional query type

        Returns:
            Message ID (UUID)
        """
        raise NotImplementedError()

    def delete_chat_session(self, chat_session_id: str) -> None:
        """Delete a chat session and all its messages.

        Args:
            chat_session_id: Chat session ID
        """
        raise NotImplementedError()

    def update_chat_session_title(self, chat_session_id: str, title: str) -> None:
        """Update a chat session's title.

        Args:
            chat_session_id: Chat session ID
            title: New title
        """
        raise NotImplementedError()

    def update_chat_session_timestamp(self, chat_session_id: str) -> None:
        """Update a chat session's updated_at timestamp.

        Args:
            chat_session_id: Chat session ID
        """
        raise NotImplementedError()
