#!/usr/bin/env python3
"""Pull all messages from the user's INBOX (not incremental).

This is intended for a one-time/full sync. For ongoing incremental
processing you should use the history API + Pub/Sub watch (see register_watch
and pull_messages). After completing a full sync you can call this script
with --save-history to write the current historyId (from users.getProfile)
to ~/.organize_mail_watch.json so future runs can be incremental.

Run as:
  cd backend
  python -m src.pull_all_inbox --limit 100 --save-history

  (Note: --workers is deprecated and no longer used)

Warnings:
- Full mailbox synces can be slow and consume API quota. Prefer history API
  for production incremental syncs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

from ..clients.gmail import (
    build_credentials_from_oauth,
    build_gmail_service,
    fetch_message,
)
from ..models.message import MailMessage
from .. import storage


def list_all_message_ids(
    service,
    user_id: str = "me",
    label_ids: Optional[List[str]] = None,
    q: Optional[str] = None
) -> List[str]:
    """Return all message IDs in the mailbox (or filtered by labels/query)."""
    ids: List[str] = []
    messages_resource = service.users().messages()
    request = messages_resource.list(userId=user_id, labelIds=label_ids, q=q, maxResults=500)
    while request is not None:
        resp = request.execute()
        for m in resp.get("messages", []):
            mid = m.get("id")
            if mid:
                ids.append(mid)
        request = messages_resource.list_next(request, resp)
    return ids


def fetch_messages_sequential(service, msg_ids: List[str], fmt: str = "full") -> List[dict]:
    """Fetch messages sequentially (no parallelism) for stability."""
    results: List[dict] = []
    total = len(msg_ids)
    failed = 0

    for i, mid in enumerate(msg_ids, 1):
        try:
            msg = fetch_message(service, mid, format=fmt)
            results.append(msg)
            if i % 10 == 0 or i == total:
                print(f"  Fetched {i}/{total} messages... ({failed} failed)", file=sys.stderr)
        except Exception as exc:
            failed += 1
            if failed <= 10:  # Only print first 10 errors
                print(f"Failed to fetch {mid}: {exc}", file=sys.stderr)
            elif failed == 11:
                print("  (suppressing further error messages...)", file=sys.stderr)

    if failed > 0:
        print(f"\n⚠️  Warning: {failed} messages failed to fetch", file=sys.stderr)

    return results


def message_summary(msg: dict) -> MailMessage:
    # Convert raw API message dict to a MailMessage object
    # Note: include_payload=True to enable attachment detection
    return MailMessage.from_api_message(msg, include_payload=True)


def save_history_id(path: str, history_id: str) -> None:
    payload = {
        "watch_response": {"historyId": history_id},
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"Saved historyId to {path}")
    except OSError as exc:
        print(f"Warning: failed to save historyId to {path}: {exc}")


def main():
    start_time = time.time()

    parser = argparse.ArgumentParser(description="Full sync: pull all messages from INBOX")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit number of messages fetched (0 = no limit)"
    )
    parser.add_argument(
        "--workers", type=int, default=8,
        help="Parallel workers for fetching"
    )
    parser.add_argument(
        "--save-history", action="store_true",
        help="After sync, save current historyId to ~/.organize_mail_watch.json"
    )
    parser.add_argument(
        "--format",
        choices=("full", "metadata", "minimal", "raw"),
        default="full",
        help="Message format to fetch (default: full, needed for attachment detection)"
    )
    args = parser.parse_args()

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH")

    if not all([client_id, client_secret, refresh_token]):
        print("Missing required env vars. Set: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH")
        sys.exit(1)

    creds = build_credentials_from_oauth(client_id, client_secret, refresh_token)
    service = build_gmail_service(credentials=creds)

    # ensure DB exists
    storage.init_db()
    existing_ids = set(storage.get_message_ids())

    print("Listing message IDs in INBOX (may take a while)...")
    list_start = time.time()
    all_ids = list_all_message_ids(service, label_ids=["INBOX"])
    list_time = time.time() - list_start
    total = len(all_ids)
    print(f"Found {total} message IDs in INBOX (took {list_time:.1f}s)")

    if args.limit > 0:
        ids_to_fetch = all_ids[: args.limit]
    else:
        ids_to_fetch = all_ids

    if not ids_to_fetch:
        print("No messages to fetch.")
        return

    # skip any IDs already stored in DB
    ids_to_fetch = [mid for mid in ids_to_fetch if mid not in existing_ids]

    if not ids_to_fetch:
        print("All messages already in database.")
        return

    print(f"Fetching {len(ids_to_fetch)} messages (format={args.format})...")
    print("Processing in batches (sequential fetching for stability)...\n")

    # Process in batches to avoid memory issues with large mailboxes
    BATCH_SIZE = 100
    total_to_fetch = len(ids_to_fetch)
    total_saved = 0
    total_failed = 0
    with_attachments = 0

    fetch_start = time.time()

    for i in range(0, len(ids_to_fetch), BATCH_SIZE):
        batch = ids_to_fetch[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(ids_to_fetch) + BATCH_SIZE - 1) // BATCH_SIZE

        print(
            f"📦 Batch {batch_num}/{total_batches}: "
            f"Fetching {len(batch)} messages...",
            file=sys.stderr
        )

        messages = fetch_messages_sequential(service, batch, fmt=args.format)
        total_failed += (len(batch) - len(messages))

        # Process and save batch immediately
        for msg in messages:
            mail_obj = message_summary(msg)
            if mail_obj.has_attachments:
                with_attachments += 1
            storage.save_message(mail_obj)
            total_saved += 1

        progress_pct = ((i + len(batch)) / total_to_fetch) * 100
        print(f"  ✓ Saved {total_saved} messages so far ({progress_pct:.1f}% complete)\n", file=sys.stderr)

    fetch_time = time.time() - fetch_start
    total_time = time.time() - start_time

    print(f"\n✅ Successfully saved {total_saved} messages to database")
    if total_failed > 0:
        print(f"⚠️  {total_failed} messages failed to fetch")
    print(f"📎 {with_attachments} messages have attachments")
    db_info = (
        storage.get_storage_backend().db_path
        if hasattr(storage.get_storage_backend(), 'db_path')
        else 'in-memory'
    )
    print(f"💾 Database: {db_info}")
    print(f"\n⏱️  Timing:")
    print(f"  List IDs:    {list_time:.1f}s")
    fetch_msg = (
        f"  Fetch+Save:  {fetch_time:.1f}s ({total_saved / fetch_time:.1f} msg/s)"
        if fetch_time > 0
        else f"  Fetch+Save:  {fetch_time:.1f}s"
    )
    print(fetch_msg)
    print("  Total:       %.1fs" % total_time)

    # Note: We don't print JSON summaries anymore since we process in batches

    if args.save_history:
        # Get current profile to obtain a historyId to use for future incremental syncs
        profile = service.users().getProfile(userId="me").execute()
        history_id = profile.get("historyId")
        if history_id:
            # save historyId to DB metadata for later incremental pulls
            storage.set_history_id(history_id)
        else:
            print("Warning: users.getProfile did not return a historyId")


if __name__ == "__main__":
    main()
