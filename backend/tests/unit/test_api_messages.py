"""Tests for the FastAPI `/messages` endpoint.

These tests exercise the API layer only (using FastAPI TestClient) and
mock the storage layer to provide deterministic responses. They verify
that the endpoint returns JSON with the expected shape and status code.
"""

from fastapi.testclient import TestClient


def test_get_messages_returns_json(monkeypatch):
    # Provide a deterministic list of message dicts from the storage shim
    sample = [{"id": "m1", "subject": "Hello"}, {"id": "m2", "subject": "World"}]

    # Patch the storage.list_messages_dicts used by the API
    monkeypatch.setattr("src.storage.list_messages_dicts", lambda limit=50, offset=0: sample)
    # Patch get_message_ids to return a count for the total
    monkeypatch.setattr("src.storage.get_message_ids", lambda: ["m1", "m2"])

    # Import app after patching to ensure it picks up the monkeypatch if needed
    from src.api import app

    client = TestClient(app)
    r = client.get("/messages?limit=10")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    
    # API now returns paginated format: {data: [...], total: N, limit: N, offset: N}
    response = r.json()
    assert "data" in response
    assert "total" in response
    assert response["data"] == sample
    assert response["total"] == 2
    assert response["limit"] == 10
    assert response["offset"] == 0
