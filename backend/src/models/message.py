from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any


@dataclass
class MailMessage:
    """Normalized representation of a Gmail message for downstream processing."""
    id: str
    thread_id: Optional[str] = None
    from_: Optional[str] = None
    to: Optional[str] = None
    subject: Optional[str] = None
    snippet: Optional[str] = None
    labels: Optional[List[str]] = None
    internal_date: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    raw: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    
    # Classification fields (populated by LLM processor)
    classification_labels: Optional[List[str]] = None
    priority: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for storage."""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "from": self.from_,
            "to": self.to,
            "subject": self.subject,
            "snippet": self.snippet,
            "labels": self.labels,
            "internal_date": self.internal_date,
            "payload": self.payload,
            "raw": self.raw,
            "headers": self.headers,
            "classification_labels": self.classification_labels,
            "priority": self.priority,
            "summary": self.summary,
        }

    @classmethod
    def from_api_message(cls, msg: Dict[str, Any], include_payload: bool = False) -> "MailMessage":
        payload = msg.get("payload") if include_payload else None
        headers_list = payload.get("headers", []) if payload else []
        headers = {h.get("name"): h.get("value") for h in headers_list if h.get("name")}

        internal_date = None
        try:
            if msg.get("internalDate") is not None:
                internal_date = int(msg.get("internalDate"))
        except (TypeError, ValueError):
            internal_date = None

        return cls(
            id=msg.get("id"),
            thread_id=msg.get("threadId"),
            from_=headers.get("From"),
            to=headers.get("To"),
            subject=headers.get("Subject"),
            snippet=msg.get("snippet"),
            labels=msg.get("labelIds"),
            internal_date=internal_date,
            payload=payload,
            raw=msg.get("raw"),
            headers=headers,
        )
