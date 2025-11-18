from __future__ import annotations

from dataclasses import dataclass, field
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
    has_attachments: bool = False

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
            "has_attachments": self.has_attachments,
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

        # Detect attachments by checking for parts with filename
        has_attachments = cls._has_attachments(payload) if payload else False

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
            has_attachments=has_attachments,
        )

    @staticmethod
    def _has_attachments(payload: Optional[Dict[str, Any]]) -> bool:
        """Check if the message payload contains attachments.

        An attachment is identified by:
        - A part with a non-empty filename, OR
        - A part with Content-Disposition header containing "attachment"
        """
        if not payload:
            return False

        def _check_part(part: Dict[str, Any]) -> bool:
            # Check for filename
            filename = part.get("filename", "")
            if filename:
                return True

            # Check for attachment disposition in headers
            headers = part.get("headers", [])
            for header in headers:
                if header.get("name", "").lower() == "content-disposition":
                    value = header.get("value", "").lower()
                    if "attachment" in value:
                        return True

            # Recursively check nested parts (multipart messages)
            parts = part.get("parts", [])
            for subpart in parts:
                if _check_part(subpart):
                    return True

            return False

        return _check_part(payload)
