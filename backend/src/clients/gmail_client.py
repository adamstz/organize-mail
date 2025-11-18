"""Gmail API helper utilities.

These helpers wrap the Google client library to keep Gmail-specific logic in one
place. They intentionally focus on read/modify access that the backend needs
once a Pub/Sub notification arrives.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Set

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import Resource, build

DEFAULT_GMAIL_SCOPES: Sequence[str] = (
    # Read-only access will not let us modify labels or ack history. We default
    # to readonly so downstream code won't attempt to modify messages unless
    # explicitly changed. Use gmail.modify only when you need to change labels
    # or state.
    "https://www.googleapis.com/auth/gmail.readonly",
)


def build_credentials_from_oauth(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    scopes: Iterable[str] = DEFAULT_GMAIL_SCOPES,
) -> OAuthCredentials:
    """Build OAuth2 credentials from client ID, secret, and refresh token.

    Use this when you have OAuth credentials (e.g., from Codespace secrets)
    instead of service account credentials.
    """
    return OAuthCredentials(
        token=None,  # Will be refreshed automatically
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(scopes),
    )


def build_gmail_service(
    credentials: Credentials | None = None,
    scopes: Iterable[str] = DEFAULT_GMAIL_SCOPES,
    *,
    cache_discovery: bool = False,
    user_agent: str | None = None,
) -> Resource:
    """Return an authenticated Gmail API client (`googleapiclient.discovery.Resource`).

    If `credentials` is omitted the function falls back to Google Application
    Default Credentials, which means it respects `GOOGLE_APPLICATION_CREDENTIALS`
    keys, `gcloud auth application-default login`, or the identity injected into
    a managed runtime. The helper also refreshes expiring credentials.
    """
    scopes_list = list(scopes)

    if credentials is None:
        scoped = scopes_list or None
        credentials, _ = google.auth.default(scopes=scoped)

    requires_scopes = getattr(credentials, "requires_scopes", False)
    if requires_scopes and scopes_list:
        credentials = credentials.with_scopes(scopes_list)

    if not credentials.valid:
        request = Request()
        credentials.refresh(request)

    discovery_kwargs = {"cache_discovery": cache_discovery}
    if user_agent:
        discovery_kwargs["client_options"] = {"user_agent": user_agent}

    return build("gmail", "v1", credentials=credentials, **discovery_kwargs)


def fetch_messages_by_history(
    gmail_service: Resource,
    start_history_id: str,
    *,
    user_id: str = "me",
    history_types: Sequence[str] | None = ("messageAdded",),
) -> List[str]:
    """Return message IDs added since `start_history_id`.

    Gmail's history API returns records per history event. We only collect the
    IDs for messages that were newly added (defaults to `messageAdded`) and we
    de-duplicate because the API can surface the same message multiple times
    across pages.
    """
    history_resource = gmail_service.users().history()  # type: ignore[attr-defined]
    request = history_resource.list(
        userId=user_id,
        startHistoryId=start_history_id,
        historyTypes=list(history_types) if history_types else None,
    )

    message_ids: List[str] = []
    seen: Set[str] = set()

    while request is not None:
        response = request.execute()
        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                message = added.get("message") or {}
                message_id = message.get("id")
                if message_id and message_id not in seen:
                    seen.add(message_id)
                    message_ids.append(message_id)

        request = history_resource.list_next(request, response)

    return message_ids


def fetch_message(
    gmail_service: Resource,
    message_id: str,
    *,
    user_id: str = "me",
    format: str = "full",
) -> dict:
    """Fetch and return a single Gmail message payload.

    The `format` argument accepts the same values as the Gmail API (`minimal`,
    `metadata`, `full`, `raw`). Downstream code can parse headers/body from the
    returned dict.
    """
    messages_resource = gmail_service.users().messages()  # type: ignore[attr-defined]
    return messages_resource.get(userId=user_id, id=message_id, format=format).execute()


def extract_message_snippet(message: dict) -> str:
    """Return the small text snippet Gmail includes in each message summary."""
    return message.get("snippet", "")


def register_watch(
    gmail_service: Resource,
    topic_name: str,
    *,
    user_id: str = "me",
    label_ids: list | None = None,
) -> dict:
    """Register a Gmail watch to publish notifications to a Pub/Sub topic.

    topic_name should be the full resource name, e.g.:
      projects/PROJECT_ID/topics/TOPIC_NAME

    Returns the API response (contains expiration and historyId).
    """
    body = {"topicName": topic_name}
    if label_ids:
        body["labelIds"] = label_ids
    return gmail_service.users().watch(userId=user_id, body=body).execute()

