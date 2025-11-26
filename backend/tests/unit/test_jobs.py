"""Tests for the job scripts that interact with Gmail helpers and storage.

This module covers higher-level job behavior by stubbing Gmail client
functions and asserting that jobs perform the expected side-effects

Tests use monkeypatching to avoid network calls and to plug an
`InMemoryStorage` implementation for deterministic assertions.
"""

import json
import sys
import types

import pytest


# Ensure the register_watch job writes the watch response JSON file to the
# user's home directory. This test stubs Gmail helpers and asserts the
# expected file is created with the returned historyId.
def test_register_watch_writes_file(monkeypatch, tmp_path):
    # set required env vars
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REFRESH", "refresh")
    monkeypatch.setenv("GMAIL_PUBSUB_TOPIC", "projects/foo/topics/bar")
    # ensure HOME is a tmp dir so we don't write to the real home
    monkeypatch.setenv("HOME", str(tmp_path))

    called = {}

    def fake_build_creds(client_id, client_secret, refresh_token):
        return None

    def fake_build_service(credentials=None):
        return None

    def fake_register_watch(service, topic):
        called['resp'] = {"historyId": "h123"}
        return called['resp']

    monkeypatch.setattr("src.clients.gmail.build_credentials_from_oauth", fake_build_creds)
    monkeypatch.setattr("src.clients.gmail.build_gmail_service", fake_build_service)
    monkeypatch.setattr("src.clients.gmail.register_watch", fake_register_watch)

    # import and run the job
    import importlib
    rw = importlib.import_module("src.jobs.register_watch")
    rw.main()

    p = tmp_path / ".organize_mail_watch.json"
    assert p.exists(), "watch file was not created"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["watch_response"]["historyId"] == "h123"


# Verify the incremental pull job fetches messages (via a stubbed
# fetch_messages_by_history) and persists them into the configured
# storage backend (InMemoryStorage in this test).
def test_pull_messages_saves_message(monkeypatch):
    # env for oauth checks
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REFRESH", "refresh")

    # use in-memory storage backend
    from src.storage import InMemoryStorage, set_storage_backend

    mem = InMemoryStorage()
    set_storage_backend(mem)
    mem.init_db()

    # set existing historyId in storage so pull_messages uses it
    from src import storage as stor
    stor.set_history_id("h0")

    # stub gmail client helpers
    monkeypatch.setattr("src.clients.gmail.build_credentials_from_oauth", lambda a,b,c: None)
    monkeypatch.setattr("src.clients.gmail.build_gmail_service", lambda credentials=None: None)
    monkeypatch.setattr("src.clients.gmail.fetch_messages_by_history", lambda service, history_id: ["m1"])

    def fake_fetch_message(service, mid, format="metadata"):
        return {
            "id": mid,
            "threadId": "t1",
            "snippet": "s",
            "internalDate": "0",
            "payload": {"headers": [{"name": "From", "value": "a@b"}, {"name": "Subject", "value": "hi"}]},
        }

    # import the job module after we've patched the clients module above
    import importlib
    pm = importlib.import_module("src.jobs.pull_messages")
    # the job module imported fetch_message at import time, so patch the
    # attribute on the job module itself
    monkeypatch.setattr(pm, "fetch_message", fake_fetch_message)

    # run the job
    pm.main()

    ids = mem.get_message_ids()
    assert "m1" in ids


# Verify the full inbox sync job iterates all message ids and saves each
# message to storage. The job's list and fetch helpers are patched to
# supply deterministic ids and message payloads.
def test_pull_all_inbox_saves_messages(monkeypatch):
    # env for oauth checks
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REFRESH", "refresh")

    # use in-memory storage backend
    from src.storage import InMemoryStorage, set_storage_backend

    mem = InMemoryStorage()
    set_storage_backend(mem)
    mem.init_db()

    # stub gmail helpers used by pull_all_inbox
    monkeypatch.setattr("src.clients.gmail.build_credentials_from_oauth", lambda a,b,c: None)
    monkeypatch.setattr("src.clients.gmail.build_gmail_service", lambda credentials=None: None)

    # patch the list_all_message_ids function defined in the job module
    import importlib
    pai = importlib.import_module("src.jobs.pull_all_inbox")
    monkeypatch.setattr(pai, "list_all_message_ids", lambda service, user_id="me", label_ids=None, q=None: ["m1", "m2"]) 

    def fake_fetch_message(service, mid, format="metadata"):
        return {"id": mid, "threadId": "t1", "snippet": "s", "payload": {"headers": [{"name": "From", "value": "a@b"}]}}

    # patch the function used inside the job module
    monkeypatch.setattr(pai, "fetch_message", fake_fetch_message)

    # run the job (no args); ensure argparse doesn't see pytest's argv
    monkeypatch.setattr(sys, "argv", ["pull_all_inbox"])
    pai.main()

    ids = set(mem.get_message_ids())
    assert {"m1", "m2"}.issubset(ids)
