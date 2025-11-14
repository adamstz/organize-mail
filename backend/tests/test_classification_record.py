from datetime import datetime, timezone

from src.models.classification_record import ClassificationRecord


def test_to_dict_and_from_dict_roundtrip():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    record = ClassificationRecord(
        id="record-1",
        message_id="msg-1",
        labels=["inbox", "todo"],
        priority="high",
        summary="Test summary",
        model="classifier-v1",
        created_at=now,
    )

    d = record.to_dict()
    assert d["id"] == "record-1"
    assert d["message_id"] == "msg-1"
    assert d["labels"] == ["inbox", "todo"]
    assert d["summary"] == "Test summary"
    assert d["created_at"] == now.isoformat()

    restored = ClassificationRecord.from_dict(d)
    assert restored.id == record.id
    assert restored.message_id == record.message_id
    assert restored.labels == record.labels
    assert restored.summary == record.summary
    assert restored.created_at == now


def test_validation_requires_ids():
    try:
        ClassificationRecord(id="", message_id="m")
        assert False, "Expected ValueError for empty id"
    except ValueError:
        pass

    try:
        ClassificationRecord(id="i", message_id="")
        assert False, "Expected ValueError for empty message_id"
    except ValueError:
        pass
