"""Job: classify stored messages using a local LLM processor.

This job reads messages from the configured storage backend, calls the
`LLMProcessor.categorize_message(subject, body)` for each message, and
writes back inferred labels/priority into storage.

Usage:
    python -m src.jobs.classify_messages [--limit N] [--dry-run]

By default this will persist labels returned by the processor. Use
`--dry-run` to only print results.
"""

import argparse
import json
from typing import List

from .. import storage
from ..models.message import MailMessage
from ..services import LLMProcessor
from ..models.classification_record import ClassificationRecord
from datetime import datetime, timezone


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="classify_messages")
    parser.add_argument("--limit", type=int, default=100, help="max messages to process")
    parser.add_argument("--dry-run", action="store_true", help="do not persist changes")
    args = parser.parse_args(argv)

    store = storage.get_storage()
    msgs: List[MailMessage] = store.list_messages(limit=args.limit)
    if not msgs:
        print("No messages to classify.")
        return

    processor = LLMProcessor()

    for m in msgs:
        subj = m.subject or ""
        # prefer snippet or payload text as the message body for classification
        body = m.snippet or (json.dumps(m.payload) if m.payload else (m.raw or ""))

        result = processor.categorize_message(subj, body)
        # expected result: dict with optional keys 'labels' (list) and 'priority' (str)
        labels = result.get("labels")
        priority = result.get("priority")

        print(f"Message {m.id}: labels={labels} priority={priority}")

        if not args.dry_run:
            if labels is not None:
                m.labels = labels
            # store priority as a label as well (simple approach)
            if priority:
                # avoid duplicates
                pr = str(priority)
                if m.labels:
                    if pr not in m.labels:
                        m.labels.append(pr)
                else:
                    m.labels = [pr]
            store.save_message(m)
            # persist a classification record for history/audit
            try:
                rec = ClassificationRecord(
                    id=f"cls-{m.id}-{datetime.now(timezone.utc).isoformat()}",
                    message_id=m.id,
                    labels=labels or [],
                    priority=priority,
                    model="llm-processor",
                    created_at=datetime.now(timezone.utc),
                )
                storage.save_classification_record(rec)
            except Exception as e:
                # non-fatal: log and continue
                print(f"Failed to persist classification record for {m.id}: {e}")


if __name__ == "__main__":
    main()
