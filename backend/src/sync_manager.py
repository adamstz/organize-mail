"""
Sync Manager - Handles background synchronization operations

This module manages:
1. Pulling messages from Gmail
2. Classifying and embedding messages
3. Tracking progress of sync operations
"""
import os
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .clients.gmail import (
    build_credentials_from_oauth,
    build_gmail_service,
    fetch_message,
)
from . import storage
from .services import LLMProcessor, EmbeddingService
from .models.message import MailMessage
import logging

logger = logging.getLogger(__name__)


class SyncProgress:
    """Tracks progress of a sync operation"""
    def __init__(self, operation_type: str):
        self.operation_type = operation_type
        self.status = "idle"  # idle, running, completed, error
        self.total = 0
        self.processed = 0
        self.errors = 0
        self.error_message = None
        self.started_at = None
        self.completed_at = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_type": self.operation_type,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "errors": self.errors,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress_percent": round((self.processed / self.total * 100) if self.total > 0 else 0, 1)
        }


class SyncManager:
    """Manages synchronization operations"""

    def __init__(self):
        self.pull_progress = SyncProgress("pull")
        self.classify_progress = SyncProgress("classify")
        self._lock = threading.Lock()

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status including counts and progress"""
        try:
            # Get database counts (database should already be initialized at startup)
            all_message_ids = storage.get_message_ids()
            db_total = len(all_message_ids)
            unclassified_ids = storage.get_unclassified_message_ids()
            unclassified_count = len(unclassified_ids)

            # Get unembedded count
            unembedded_count = self._get_unembedded_count()

            # Get Gmail INBOX count
            gmail_total = self._get_gmail_inbox_count()
            not_synced = max(0, gmail_total - db_total) if gmail_total is not None else 0

            return {
                "gmail_total": gmail_total,
                "db_total": db_total,
                "not_synced": not_synced,
                "unclassified": unclassified_count,
                "unembedded": unembedded_count,
                "pull_progress": self.pull_progress.to_dict(),
                "classify_progress": self.classify_progress.to_dict()
            }
        except Exception as e:
            logger.error(f"Error getting sync status: {e}", exc_info=True)
            return {
                "error": str(e),
                "gmail_total": None,
                "db_total": 0,
                "not_synced": 0,
                "unclassified": 0,
                "unembedded": 0,
                "pull_progress": self.pull_progress.to_dict(),
                "classify_progress": self.classify_progress.to_dict()
            }

    def _get_gmail_inbox_count(self) -> Optional[int]:
        """Get total count of messages in Gmail INBOX"""
        try:
            client_id = os.environ.get("GOOGLE_CLIENT_ID")
            client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
            refresh_token = os.environ.get("GOOGLE_REFRESH")

            if not all([client_id, client_secret, refresh_token]):
                return None

            creds = build_credentials_from_oauth(client_id, client_secret, refresh_token)
            service = build_gmail_service(credentials=creds)

            # Get message count from INBOX label
            result = service.users().messages().list(
                userId="me",
                labelIds=["INBOX"],
                maxResults=1
            ).execute()

            # The resultSizeEstimate gives us the total count
            return result.get("resultSizeEstimate", 0)

        except Exception as e:
            logger.debug(f"Gmail not available: {e}")
            return None

    def _get_unembedded_count(self) -> int:
        """Get count of messages without embeddings"""
        try:
            backend = storage.get_storage_backend()
            conn = backend.connect()
            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(DISTINCT m.id)
                FROM messages m
                LEFT JOIN email_chunks ec ON m.id = ec.message_id
                WHERE m.embedding IS NULL
                  AND ec.message_id IS NULL
            """)

            count = cur.fetchone()[0]
            cur.close()
            conn.close()

            return count
        except Exception as e:
            logger.error(f"Error getting unembedded count: {e}")
            return 0

    def start_pull(self) -> bool:
        """Start pulling messages from Gmail in background"""
        with self._lock:
            if self.pull_progress.status == "running":
                return False

            # Reset progress
            self.pull_progress = SyncProgress("pull")
            self.pull_progress.status = "running"
            self.pull_progress.started_at = datetime.now(timezone.utc)

            # Start background thread
            thread = threading.Thread(target=self._pull_messages_background)
            thread.daemon = True
            thread.start()

            return True

    def _pull_messages_background(self):
        """Background task to pull messages from Gmail"""
        try:
            logger.info("Starting Gmail pull operation")

            # Get Gmail credentials
            client_id = os.environ.get("GOOGLE_CLIENT_ID")
            client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
            refresh_token = os.environ.get("GOOGLE_REFRESH")

            if not all([client_id, client_secret, refresh_token]):
                raise Exception("Gmail credentials not configured")

            creds = build_credentials_from_oauth(client_id, client_secret, refresh_token)
            service = build_gmail_service(credentials=creds)

            # Initialize storage
            storage.init_db()
            existing_ids = set(storage.get_message_ids())

            # List all message IDs from INBOX
            logger.info("Listing message IDs from Gmail INBOX")
            all_ids = []
            messages_resource = service.users().messages()
            request = messages_resource.list(userId="me", labelIds=["INBOX"], maxResults=500)

            while request is not None:
                resp = request.execute()
                for m in resp.get("messages", []):
                    mid = m.get("id")
                    if mid:
                        all_ids.append(mid)
                request = messages_resource.list_next(request, resp)

            # Filter to only new messages
            ids_to_fetch = [mid for mid in all_ids if mid not in existing_ids]

            self.pull_progress.total = len(ids_to_fetch)
            logger.info(f"Found {len(ids_to_fetch)} new messages to pull")

            if len(ids_to_fetch) == 0:
                self.pull_progress.status = "completed"
                self.pull_progress.completed_at = datetime.now(timezone.utc)
                logger.info("No new messages to pull")
                return

            # Fetch and save messages
            for i, msg_id in enumerate(ids_to_fetch):
                try:
                    # Fetch message
                    msg_data = fetch_message(service, msg_id, format="full")
                    mail_obj = MailMessage.from_api_message(msg_data, include_payload=True)

                    # Save to database
                    storage.save_message(mail_obj)

                    self.pull_progress.processed += 1

                    if (i + 1) % 10 == 0 or (i + 1) == len(ids_to_fetch):
                        logger.info(f"Pulled {i + 1}/{len(ids_to_fetch)} messages")

                except Exception as e:
                    logger.error(f"Error fetching message {msg_id}: {e}")
                    self.pull_progress.errors += 1

            self.pull_progress.status = "completed"
            self.pull_progress.completed_at = datetime.now(timezone.utc)
            logger.info(f"Pull completed: {self.pull_progress.processed} messages pulled, {self.pull_progress.errors} errors")

        except Exception as e:
            logger.error(f"Pull operation failed: {e}", exc_info=True)
            self.pull_progress.status = "error"
            self.pull_progress.error_message = str(e)
            self.pull_progress.completed_at = datetime.now(timezone.utc)

    def start_classify(self) -> bool:
        """Start classifying and embedding messages in background"""
        with self._lock:
            if self.classify_progress.status == "running":
                return False

            # Reset progress
            self.classify_progress = SyncProgress("classify")
            self.classify_progress.status = "running"
            self.classify_progress.started_at = datetime.now(timezone.utc)

            # Start background thread
            thread = threading.Thread(target=self._classify_messages_background)
            thread.daemon = True
            thread.start()

            return True

    def _classify_messages_background(self):
        """Background task to classify and embed unclassified messages"""
        try:
            logger.info("Starting classify and embed operation")

            # Initialize services (database should already be initialized at startup)
            processor = LLMProcessor()
            embedder = EmbeddingService()

            # Get unclassified messages
            unclassified_ids = storage.get_unclassified_message_ids()
            self.classify_progress.total = len(unclassified_ids)

            logger.info(f"Found {len(unclassified_ids)} unclassified messages")

            if len(unclassified_ids) == 0:
                self.classify_progress.status = "completed"
                self.classify_progress.completed_at = datetime.now(timezone.utc)
                logger.info("No unclassified messages to process")
                return

            # Process messages one by one
            for i, msg_id in enumerate(unclassified_ids):
                try:
                    # Load message
                    msg = storage.get_message_by_id(msg_id)
                    if not msg:
                        logger.warning(f"Could not load message {msg_id}")
                        self.classify_progress.errors += 1
                        continue

                    # Extract body text
                    body = msg.snippet or ""
                    if msg.payload and isinstance(msg.payload, dict):
                        parts = msg.payload.get("parts", [])
                        for part in parts:
                            if part.get("mimeType") == "text/plain":
                                body_data = part.get("body", {}).get("data", "")
                                if body_data:
                                    try:
                                        import base64
                                        missing_padding = len(body_data) % 4
                                        if missing_padding:
                                            body_data += '=' * (4 - missing_padding)
                                        body = base64.b64decode(body_data).decode("utf-8", errors="ignore")
                                        break
                                    except Exception:
                                        pass

                    # Classify
                    result = processor.categorize_message(msg.subject or "", body)
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

                    # Embed
                    subject = msg.subject or ""
                    from_addr = msg.from_ or ""
                    email_text = f"From: {from_addr}\nSubject: {subject}\n\n{body}"
                    embedding = embedder.embed_text(email_text)

                    # Store embedding
                    backend = storage.get_storage_backend()
                    conn = backend.connect()
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE messages
                        SET embedding = %s, embedding_model = %s, embedded_at = %s
                        WHERE id = %s
                        """,
                        (embedding, embedder.model_name, datetime.now(timezone.utc), msg.id)
                    )
                    conn.commit()
                    cur.close()
                    conn.close()

                    self.classify_progress.processed += 1

                    if (i + 1) % 5 == 0 or (i + 1) == len(unclassified_ids):
                        logger.info(f"Processed {i + 1}/{len(unclassified_ids)} messages")

                except Exception as e:
                    error_msg = f"❌ Error processing message {msg_id}: {e}"
                    logger.error(error_msg, exc_info=True)
                    print(f"\n{error_msg}")
                    print(f"Exception type: {type(e).__name__}")
                    import traceback
                    traceback.print_exc()
                    self.classify_progress.errors += 1

            self.classify_progress.status = "completed"
            self.classify_progress.completed_at = datetime.now(timezone.utc)
            logger.info(
                f"Classify completed: {self.classify_progress.processed} messages processed, "
                f"{self.classify_progress.errors} errors"
            )

        except Exception as e:
            logger.error(f"Classify operation failed: {e}", exc_info=True)
            self.classify_progress.status = "error"
            self.classify_progress.error_message = str(e)
            self.classify_progress.completed_at = datetime.now(timezone.utc)


# Global sync manager instance
_sync_manager: Optional[SyncManager] = None


def get_sync_manager() -> SyncManager:
    """Get or create the global sync manager instance"""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager()
    return _sync_manager
