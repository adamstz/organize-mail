from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class ClassificationRecord:
    """A small, stable, serializable record for persisted classification results.

    Stored separately so we can keep a history of classifier outputs and
    reference the originating message by id.

    Implementation notes:
    - `labels` defaults to an empty list to simplify callers (no None checks).
    - `created_at` is an in-memory `datetime` and is serialized to ISO 8601 via
      `to_dict()`; `from_dict()` will rehydrate it.
    """
    id: str
    message_id: str
    labels: List[str] = field(default_factory=list)
    priority: Optional[str] = None
    summary: Optional[str] = None
    model: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        # Basic validation to catch common mistakes early.
        if not self.id:
            raise ValueError("ClassificationRecord.id must be provided and non-empty")
        if not self.message_id:
            raise ValueError("ClassificationRecord.message_id must be provided and non-empty")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict. Datetimes are converted to ISO strings."""
        data = asdict(self)
        # asdict keeps datetime objects as-is; convert created_at to ISO string.
        if self.created_at is not None:
            data["created_at"] = self.created_at.isoformat()
        else:
            data["created_at"] = None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationRecord":
        """Create a ClassificationRecord from a dict produced by `to_dict()`.

        Accepts created_at as an ISO string or a datetime object (or None).
        """
        created = data.get("created_at")
        created_dt: Optional[datetime]
        if isinstance(created, str):
            # datetime.fromisoformat handles most ISO-8601 strings produced by
            # datetime.isoformat(), including with timezone offsets.
            created_dt = datetime.fromisoformat(created)
        else:
            created_dt = created

        labels = data.get("labels") or []

        return cls(
            id=data["id"],
            message_id=data["message_id"],
            labels=list(labels),
            priority=data.get("priority"),
            summary=data.get("summary"),
            model=data.get("model"),
            created_at=created_dt,
        )
