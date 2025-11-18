#!/usr/bin/env python3
"""Pull messages since the last registered Gmail watch historyId.

This module is designed to run as `python -m src.pull_messages` from the
`backend/` directory.
"""
from __future__ import annotations

import json
import os
import sys
from typing import List

from ..clients.gmail import (
    build_credentials_from_oauth,
    build_gmail_service,
    fetch_messages_by_history,
    fetch_message,
)
from ..models.message import MailMessage
from .. import storage


def load_watch_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        print(f"Failed to open watch file {path}: {exc}")
        return None


def pretty_print_message(msg: dict) -> None:
    # Convert to MailMessage and print a small summary
    mail = MailMessage.from_api_message(msg, include_payload=False)
    print(f"---\nFrom: {mail.from_}\nSubject: {mail.subject}\nSnippet: {mail.snippet}\n")


def main():
    home = os.path.expanduser("~")
    # prefer historyId saved in DB metadata; fall back to the watch file
    history_id = storage.get_history_id()
    save_path = os.path.join(home, ".organize_mail_watch.json")
    if not history_id:
        data = load_watch_file(save_path)
        if not data:
            print(f"No watch file found at {save_path} and no historyId in DB. Run register_watch first.")
            sys.exit(1)
        watch_resp = data.get("watch_response", {})
        history_id = watch_resp.get("historyId")
    if not history_id:
        print("No historyId found in saved watch response. Run register_watch again.")
        sys.exit(1)

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH")

    if not all([client_id, client_secret, refresh_token]):
        print("Missing required env vars. Set: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH")
        sys.exit(1)

    creds = build_credentials_from_oauth(client_id, client_secret, refresh_token)
    service = build_gmail_service(credentials=creds)

    print(f"Fetching messages since historyId: {history_id}")
    message_ids: List[str] = fetch_messages_by_history(service, history_id)

    if not message_ids:
        print("No new messages found since the saved historyId.")
        return

    print(f"Found {len(message_ids)} message(s). Fetching details...")
    for mid in message_ids:
        msg = fetch_message(service, mid)
        # convert to model and save
        mail = MailMessage.from_api_message(msg, include_payload=False)
        storage.save_message(mail)
        pretty_print_message(msg)

    # update stored historyId to the latest processed value
    # Gmail history.list responses don't return a single new historyId; use
    # users.getProfile() to obtain a current cursor for next time
    try:
        profile = service.users().getProfile(userId="me").execute()
        new_history_id = profile.get("historyId")
        if new_history_id:
            storage.set_history_id(new_history_id)
    except Exception:
        # non-fatal: we've already saved messages
        pass


if __name__ == "__main__":
    main()
