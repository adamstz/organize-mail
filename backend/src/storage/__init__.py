"""Storage package public surface.

This re-exports the functions and classes from the internal `storage.py`
shim and the sqlite backend so older import paths like
`from src.storage import InMemoryStorage` and `from src.sqlite_storage import SQLiteStorage`
continue to work.
"""
from .storage import (
    storage_factory_from_env,
    set_storage_backend,
    get_storage_backend,
    init_db,
    save_message,
    get_message_ids,
    get_message_by_id,
    get_unclassified_message_ids,
    count_classified_messages,
    list_messages,
    list_messages_dicts,
    create_classification,
    get_latest_classification,
    save_classification_record,
    update_message_latest_classification,
    list_classification_records_for_message,
    get_history_id,
    set_history_id,
    get_label_counts,
    list_messages_by_label,
    list_messages_by_priority,
    list_classified_messages,
    list_unclassified_messages,
    list_messages_by_filters,
)
from .sqlite_storage import SQLiteStorage, default_db_path
from .memory_storage import InMemoryStorage

# PostgresStorage is imported lazily in storage_factory_from_env to avoid
# requiring psycopg2 when using SQLite or InMemory backends

__all__ = [
    # shim
    "storage_factory_from_env",
    "set_storage_backend",
    "get_storage_backend",
    "init_db",
    "save_message",
    "get_message_ids",
    "get_message_by_id",
    "get_unclassified_message_ids",
    "count_classified_messages",
    "list_messages",
    "list_messages_dicts",
    "create_classification",
    "get_latest_classification",
    "save_classification_record",
    "update_message_latest_classification",
    "list_classification_records_for_message",
    "get_history_id",
    "set_history_id",
    "get_label_counts",
    "list_messages_by_label",
    "list_messages_by_priority",
    "list_classified_messages",
    "list_unclassified_messages",
    "list_messages_by_filters",
    "InMemoryStorage",
    # sqlite
    "SQLiteStorage",
    "default_db_path",
]
