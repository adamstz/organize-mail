"""Pluggable storage shim that delegates to a chosen backend implementation.

This module provides a unified interface for different storage backends:
- SQLite: File-based storage (sqlite_storage.py)
- PostgreSQL: Remote database storage (postgres_storage.py)
- Memory: In-memory storage for testing (memory_storage.py)

The STORAGE_BACKEND environment variable must be set to one of:
'sqlite', 'postgres', or 'memory'. No default is provided to ensure
explicit configuration.

To swap backends at runtime, call `set_storage_backend()` with an object
that implements the StorageBackend interface (see storage_interface.py).
"""
from __future__ import annotations

from typing import List, Optional
import os

from ..models.message import MailMessage
from .storage_interface import StorageBackend
from .sqlite_storage import SQLiteStorage, default_db_path


def storage_factory_from_env() -> StorageBackend:
    """Create a storage backend instance based on STORAGE_BACKEND env var.

    Supported values:
      - sqlite (requires explicit setting)
      - postgres (requires DATABASE_URL or DB_* env vars)
      - memory (requires explicit setting)

    STORAGE_BACKEND must be explicitly set - no default is provided.

    For postgres, you can either set DATABASE_URL directly, or use these individual vars:
      - DB_USER (or POSTGRES_USER for backwards compatibility)
      - DB_PASSWORD (or POSTGRES_PASSWORD)
      - DB_HOST (or POSTGRES_HOST) - the host/proxy to connect to (e.g., localhost for cloudflared)
      - DB_PORT (or POSTGRES_PORT) - the port to connect to (e.g., 5433 for cloudflared proxy)
      - DB_NAME (or POSTGRES_DB) - the database name
    """
    mode = os.environ.get("STORAGE_BACKEND")
    if not mode:
        raise ValueError(
            "STORAGE_BACKEND environment variable is required. "
            "Set to 'sqlite', 'postgres', or 'memory'"
        )

    mode = mode.lower()
    if mode == "memory" or mode == "inmemory":
        from .memory_storage import InMemoryStorage
        return InMemoryStorage()
    elif mode == "postgres" or mode == "postgresql":
        from .postgres_storage import PostgresStorage
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            # Build from individual components if DATABASE_URL not set
            # Note: These refer to the connection endpoint (which may be a local proxy like cloudflared)
            user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER", "postgres")
            password = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")
            host = os.environ.get("DB_HOST") or os.environ.get("POSTGRES_HOST", "localhost")
            port = os.environ.get("DB_PORT") or os.environ.get("POSTGRES_PORT", "5433")
            database = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB", "mail_db")
            db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return PostgresStorage(db_url=db_url)
    elif mode == "sqlite":
        db_path = os.environ.get("STORAGE_DB_PATH") or default_db_path()
        return SQLiteStorage(db_path=db_path)
    else:
        raise ValueError(
            f"Unknown STORAGE_BACKEND: {mode}. "
            "Supported values: 'sqlite', 'postgres', 'memory'"
        )


# default backend instance (lazy-initialized on first use)
_backend: Optional[StorageBackend] = None


def set_storage_backend(backend: StorageBackend) -> None:
    global _backend
    _backend = backend


def get_storage_backend() -> StorageBackend:
    """Get the global storage backend, initializing from env if needed."""
    global _backend
    if _backend is None:
        _backend = storage_factory_from_env()
    return _backend


def init_db() -> None:
    get_storage_backend().init_db()


def save_message(msg: MailMessage) -> None:
    get_storage_backend().save_message(msg)


def get_message_ids() -> List[str]:
    return get_storage_backend().get_message_ids()


def get_message_by_id(message_id: str) -> Optional[MailMessage]:
    """Get a single message by ID."""
    return get_storage_backend().get_message_by_id(message_id)


def get_unclassified_message_ids() -> List[str]:
    """Get IDs of messages that haven't been classified yet."""
    return get_storage_backend().get_unclassified_message_ids()


def count_classified_messages() -> int:
    """Count how many messages have been classified."""
    return get_storage_backend().count_classified_messages()


def list_messages(limit: int = 100, offset: int = 0) -> List[MailMessage]:
    return get_storage_backend().list_messages(limit=limit, offset=offset)


def create_classification(message_id: str, labels: List[str], priority: str, summary: str, model: str = None) -> str:
    """Create a new classification and link it to a message.

    Returns the classification ID.
    """
    return get_storage_backend().create_classification(message_id, labels, priority, summary, model)


def get_latest_classification(message_id: str) -> Optional[dict]:
    """Get the most recent classification for a message.

    Returns dict with: id, labels, priority, summary, model, created_at
    """
    return get_storage_backend().get_latest_classification(message_id)


def save_classification_record(record) -> None:
    get_storage_backend().save_classification_record(record)


def update_message_latest_classification(message_id: str, classification_id: str) -> None:
    """Update the latest_classification_id for a message."""
    get_storage_backend().update_message_latest_classification(message_id, classification_id)


def list_classification_records_for_message(message_id: str):
    return get_storage_backend().list_classification_records_for_message(message_id)


def list_messages_dicts(limit: int = 100, offset: int = 0) -> List[dict]:
    """Return serializable dicts for messages suitable for JSON responses.

    This acts like a small stored-procedure helper for the API layer.
    """
    msgs = get_storage_backend().list_messages(limit=limit, offset=offset)
    dicts: List[dict] = []
    for m in msgs:
        d = m.to_dict()
        dicts.append(d)
    return dicts


def get_history_id() -> Optional[str]:
    return get_storage_backend().get_history_id()


def set_history_id(history_id: str) -> None:
    get_storage_backend().set_history_id(history_id)


def get_label_counts() -> dict:
    """Get all unique classification labels with their counts."""
    return get_storage_backend().get_label_counts()


def list_messages_by_label(label: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
    """List messages filtered by classification label with database-level filtering.

    Returns tuple of (messages, total_count).
    """
    return get_storage_backend().list_messages_by_label(label, limit=limit, offset=offset)


def list_messages_by_priority(priority: str, limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
    """List messages filtered by priority with database-level filtering.

    Returns tuple of (messages, total_count).
    """
    return get_storage_backend().list_messages_by_priority(priority, limit=limit, offset=offset)


def list_classified_messages(limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
    """List only classified messages with database-level filtering.

    Returns tuple of (messages, total_count).
    """
    return get_storage_backend().list_classified_messages(limit=limit, offset=offset)


def list_unclassified_messages(limit: int = 100, offset: int = 0) -> tuple[List[MailMessage], int]:
    """List only unclassified messages with database-level filtering.

    Returns tuple of (messages, total_count).
    """
    return get_storage_backend().list_unclassified_messages(limit=limit, offset=offset)


def list_messages_by_filters(
    priority: Optional[str] = None,
    labels: Optional[List[str]] = None,
    classified: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple[List[MailMessage], int]:
    """List messages with combined filters using database-level filtering.

    Args:
        priority: Filter by priority (e.g., "high", "medium", "low")
        labels: Filter by labels - message must have ALL specified labels
        classified: If True, only classified messages. If False, only unclassified. If None, all.
        limit: Max messages to return
        offset: Skip this many results

    Returns tuple of (messages, total_count).
    """
    return get_storage_backend().list_messages_by_filters(
        priority=priority,
        labels=labels,
        classified=classified,
        limit=limit,
        offset=offset
    )


# Chat session methods
def create_chat_session(title: Optional[str] = None) -> str:
    """Create a new chat session and return its ID."""
    return get_storage_backend().create_chat_session(title=title)


def list_chat_sessions(limit: int = 50, offset: int = 0) -> List[dict]:
    """List chat sessions ordered by most recently updated."""
    return get_storage_backend().list_chat_sessions(limit=limit, offset=offset)


def get_chat_session_messages(chat_session_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
    """Get all messages for a chat session ordered by timestamp."""
    return get_storage_backend().get_chat_session_messages(chat_session_id=chat_session_id, limit=limit, offset=offset)


def save_message_to_chat_session(
    chat_session_id: str,
    role: str,
    content: str,
    sources: Optional[List[dict]] = None,
    confidence: Optional[str] = None,
    query_type: Optional[str] = None
) -> str:
    """Save a message to a chat session and return message ID."""
    return get_storage_backend().save_message_to_chat_session(
        chat_session_id=chat_session_id,
        role=role,
        content=content,
        sources=sources,
        confidence=confidence,
        query_type=query_type
    )


def delete_chat_session(chat_session_id: str) -> None:
    """Delete a chat session and all its messages."""
    get_storage_backend().delete_chat_session(chat_session_id=chat_session_id)


def update_chat_session_title(chat_session_id: str, title: str) -> None:
    """Update the title of a chat session."""
    get_storage_backend().update_chat_session_title(chat_session_id=chat_session_id, title=title)


def update_chat_session_timestamp(chat_session_id: str) -> None:
    """Update the updated_at timestamp of a chat session."""
    get_storage_backend().update_chat_session_timestamp(chat_session_id=chat_session_id)
