#!/usr/bin/env python3
"""Classify all messages in the database using the LLM processor.

This script:
1. Retrieves all messages from the database
2. Classifies each message using the configured LLM provider
3. Updates the message with classification data (labels, priority, summary)
4. Skips messages that are already classified
5. Shows progress with time estimates

Usage:
    python -m src.jobs.classify_all [--force] [--limit N]
"""

import argparse
import sys
import time

from ..models.message import MailMessage
from .. import storage
from ..services import LLMProcessor


def is_classified(msg: MailMessage) -> bool:
    """Check if a message already has classification data."""
    return (
        msg.classification_labels is not None or
        msg.priority is not None or
        msg.summary is not None
    )


def format_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def classify_all_messages(force: bool = False, limit: int = None) -> None:
    """Classify all messages in the database."""

    print("🔍 Loading messages from database...")
    storage.init_db()

    # Get total message count
    total_messages = len(storage.get_message_ids())

    if total_messages == 0:
        print("❌ No messages found in database.")
        print("💡 Tip: Run pull_all_inbox.py or pull_messages.py first to fetch messages.")
        return

    print(f"📊 Found {total_messages} messages in database")

    if not force:
        # Efficiently count classified messages without loading them all
        print("🔍 Checking classification status...")
        already_classified = storage.count_classified_messages()

        if already_classified > 0:
            print(f"✓ {already_classified} messages already classified")

        # Get unclassified message IDs efficiently
        unclassified_ids = storage.get_unclassified_message_ids()
        num_to_classify = len(unclassified_ids)

        if num_to_classify == 0:
            print("✅ All messages are already classified!")
            return

        print(f"📝 Messages to classify: {num_to_classify}")
    else:
        print("⚠️  Force mode: Re-classifying all messages")
        unclassified_ids = storage.get_message_ids()
        num_to_classify = len(unclassified_ids)

    if limit:
        unclassified_ids = unclassified_ids[:limit]
        num_to_classify = len(unclassified_ids)
        print(f"� Limiting to {limit} messages")

    print()

    # Initialize LLM processor
    processor = LLMProcessor()
    print(f"🤖 Using LLM provider: {processor.provider}")
    if getattr(processor, "model", None):
        print(f"🤖 Model: {processor.model}")
    print()

    # Start classification
    print("🚀 Starting classification...")
    print("-" * 60)

    start_time = time.time()
    classified_count = 0
    error_count = 0

    # Process messages by loading them one at a time by ID
    for i, msg_id in enumerate(unclassified_ids, 1):
        msg_start = time.time()

        # Load the message by ID
        msg = storage.get_message_by_id(msg_id)

        if not msg:
            print(f"⚠️  Warning: Could not load message {msg_id}")
            error_count += 1
            continue

        # Calculate time estimates
        if i > 1:
            elapsed = time.time() - start_time
            avg_time_per_msg = elapsed / (i - 1)
            remaining = (num_to_classify - i + 1) * avg_time_per_msg
            eta = format_time(remaining)
        else:
            eta = "calculating..."

        # Show progress
        subject = msg.subject or "(no subject)"
        subject_preview = subject[:50] + "..." if len(subject) > 50 else subject
        print(f"[{i}/{num_to_classify}] {subject_preview}")
        print(f"  ID: {msg.id[:20]}... | ETA: {eta}")

        try:
            # Classify the message - try to get full body, fallback to snippet
            body = msg.snippet or ""

            # Try to decode full email body from payload
            payload = getattr(msg, "payload", None)
            if payload and isinstance(payload, dict):
                parts = payload.get("parts", [])
                for part in parts:
                    if part.get("mimeType") == "text/plain":
                        body_data = part.get("body", {}).get("data", "")
                        if body_data:
                            try:
                                import base64
                                # Add padding if needed for base64 decoding
                                missing_padding = len(body_data) % 4
                                if missing_padding:
                                    body_data += '=' * (4 - missing_padding)
                                body = base64.b64decode(body_data).decode("utf-8", errors="ignore")
                                break
                            except Exception:
                                # If decoding fails, just use snippet
                                pass

            # Classify with LLM - will raise exception if it fails
            result = processor.categorize_message(msg.subject or "", body)

            # Create classification record (new approach - stores in separate table)
            labels = result.get("labels", [])
            priority = result.get("priority", "normal")
            summary = result.get("summary", "")
            model_name = f"{processor.provider}:{processor.model}" if hasattr(processor, 'model') else processor.provider

            storage.create_classification(
                message_id=msg.id,
                labels=labels,
                priority=priority,
                summary=summary,
                model=model_name
            )

            # Show result
            labels_str = ", ".join(labels) if labels else "none"
            summary_preview = summary[:60] + "..." if len(summary) > 60 else summary
            print(f"  ✓ {priority} priority | labels: {labels_str}")
            print(f"  📝 {summary_preview}")

            msg_time = time.time() - msg_start
            print(f"  ⏱️  {msg_time:.2f}s")

            classified_count += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            error_count += 1

        print()

    # Final summary
    total_time = time.time() - start_time
    print("-" * 60)
    print("📊 Classification Complete!")
    print()
    print(f"✅ Successfully classified: {classified_count}")
    if error_count > 0:
        print(f"❌ Errors: {error_count}")
    print(f"⏱️  Total time: {format_time(total_time)}")

    if classified_count > 0:
        avg_time = total_time / classified_count
        print(f"⏱️  Average time per message: {avg_time:.2f}s")

    print()
    print(f"💾 Database: {storage.get_storage_backend().db_path if hasattr(storage.get_storage_backend(), 'db_path') else 'in-memory'}")


def main():
    parser = argparse.ArgumentParser(
        description="Classify all messages in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.jobs.classify_all                    # Classify unclassified messages
  python -m src.jobs.classify_all --force            # Re-classify all messages
  python -m src.jobs.classify_all --limit 10         # Only classify 10 messages
  python -m src.jobs.classify_all --force --limit 5
  # Re-classify first 5 messages (useful for testing)
        """
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-classify messages even if they already have classification data"
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Only process N messages (useful for testing)"
    )

    args = parser.parse_args()

    try:
        classify_all_messages(force=args.force, limit=args.limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  Classification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
