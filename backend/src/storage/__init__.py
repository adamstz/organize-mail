"""Storage package public surface.

This re-exports the functions and classes from the internal `storage.py`
shim and the sqlite backend so older import paths like
`from src.storage import InMemoryStorage` and `from src.sqlite_storage import SQLiteStorage`
continue to work.
"""
from .storage import *
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
    "list_messages",
    "get_history_id",
    "set_history_id",
    "InMemoryStorage",
    # sqlite
    "SQLiteStorage",
    "default_db_path",
]
