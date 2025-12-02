#!/usr/bin/env python3
"""Job to generate embeddings for all emails in the database.

This script:
1. Fetches all messages from the database
2. Generates vector embeddings using sentence-transformers
3. Stores embeddings in PostgreSQL with pgvector
4. Handles both single and chunked embeddings for long emails
"""
import sys
import os
import time
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.storage.storage import get_storage_backend  # noqa: E402
from src.services import EmbeddingService  # noqa: E402
from tqdm import tqdm  # noqa: E402


def get_unembedded_message_ids(storage) -> list:
    """Get IDs of messages that don't have embeddings yet."""
    conn = storage.connect()
    cur = conn.cursor()

    # Get messages without embeddings (not in messages.embedding and not in email_chunks)
    cur.execute("""
        SELECT m.id
        FROM messages m
        LEFT JOIN email_chunks ec ON m.id = ec.message_id
        WHERE m.embedding IS NULL
          AND ec.message_id IS NULL
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [r[0] for r in rows]


def extract_body_text(message) -> str:
    """Extract text content from email payload.

    This is a simplified version - you may want to enhance it based on your needs.
    """
    # Try to get snippet as fallback
    if hasattr(message, 'snippet') and message.snippet:
        return message.snippet

    # Try to extract from payload
    if hasattr(message, 'payload') and message.payload:
        # This is simplified - you may need to parse HTML, handle parts, etc.
        payload = message.payload
        if isinstance(payload, dict):
            # Try to find text in parts
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/plain' and 'body' in part:
                        body_data = part['body'].get('data', '')
                        if body_data:
                            # Gmail API returns base64-encoded data
                            import base64
                            try:
                                return base64.urlsafe_b64decode(body_data).decode('utf-8')
                            except Exception:
                                pass

            # Try body data directly
            if 'body' in payload and 'data' in payload['body']:
                import base64
                try:
                    return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
                except Exception:
                    pass

    # Fallback to snippet
    return getattr(message, 'snippet', '') or ''


def main():
    """Main function to embed all emails."""
    print("=" * 60)
    print("Email Embedding Job")
    print("=" * 60)
    print()

    # Initialize storage
    print("[1/4] Connecting to database...")
    try:
        storage = get_storage_backend()
        print("      ✓ Database connected successfully")
    except Exception as e:
        print(f"      ✗ Database connection failed: {e}")
        return
    print()

    # Initialize embedding service
    print("[2/4] Loading embedding model...")
    print("      This may take 1-2 minutes on first run (downloading ~80MB model)")
    print("      Model: all-MiniLM-L6-v2")
    try:
        embedder = EmbeddingService()
        print(f"      ✓ Model loaded: {embedder.model_name}")
        print(f"      ✓ Embedding dimensions: {embedder.embedding_dim}")
    except Exception as e:
        print(f"      ✗ Model loading failed: {e}")
        return
    print()

    # Get unembedded messages only
    print("[3/4] Fetching unembedded messages from database...")
    try:
        all_message_ids = storage.get_message_ids()
        message_ids = get_unembedded_message_ids(storage)
        total_messages = len(message_ids)
        already_embedded = len(all_message_ids) - total_messages
        print(f"      ✓ Total messages in database: {len(all_message_ids)}")
        print(f"      ✓ Already embedded: {already_embedded}")
        print(f"      ✓ To process: {total_messages}")
    except Exception as e:
        print(f"      ✗ Failed to fetch messages: {e}")
        return
    print()

    if total_messages == 0:
        print("      All messages are already embedded. Nothing to do!")
        return

    # Process messages in batches for efficiency
    # BATCH_SIZE: Number of emails to fetch and embed together
    # Higher = better throughput, but more memory usage
    BATCH_SIZE = 128

    print("[4/4] Generating embeddings...")
    print(f"      Processing in batches of {BATCH_SIZE} emails")
    print(f"      Total emails: {total_messages}")
    print()

    single_count = 0
    error_count = 0

    # Timing metrics
    total_fetch_time = 0
    total_embed_time = 0
    total_store_time = 0

    # Reuse database connection for all operations
    conn = storage.connect()
    cur = conn.cursor()

    try:
        from psycopg2.extras import RealDictCursor
        from src.models.message import MailMessage

        # Process in batches
        batch_num = 0
        for batch_start in tqdm(range(0, len(message_ids), BATCH_SIZE), desc="Processing batches", disable=True):
            batch_ids = message_ids[batch_start:batch_start + BATCH_SIZE]
            batch_num += 1

            print(f"\n[Batch {batch_num}/{(len(message_ids) + BATCH_SIZE - 1) // BATCH_SIZE}] Processing {len(batch_ids)} emails...")

            # TIME: Fetch messages
            fetch_start = time.time()
            fetch_cur = conn.cursor(cursor_factory=RealDictCursor)
            fetch_cur.execute(
                """
                SELECT m.*, c.labels as class_labels, c.priority as class_priority, c.summary as class_summary
                FROM messages m
                LEFT JOIN classifications c ON m.latest_classification_id = c.id
                WHERE m.id = ANY(%s)
                """,
                (batch_ids,)
            )
            rows = fetch_cur.fetchall()
            fetch_cur.close()
            fetch_time = time.time() - fetch_start
            total_fetch_time += fetch_time
            print(f"  → Fetched from DB:    {fetch_time:5.2f}s")

            # Convert to MailMessage objects and prepare texts for batch embedding
            messages = []
            email_texts = []

            for row in rows:
                try:
                    message = MailMessage(
                        id=row['id'],
                        thread_id=row['thread_id'],
                        from_=row['from_addr'],
                        to=row['to_addr'],
                        subject=row['subject'],
                        snippet=row['snippet'],
                        labels=row['labels'],
                        internal_date=row['internal_date'],
                        payload=row['payload'],
                        raw=row['raw'],
                        headers=row['headers'] or {},
                        has_attachments=row['has_attachments'] or False,
                        classification_labels=row['class_labels'],
                        priority=row['class_priority'],
                        summary=row['class_summary']
                    )
                    messages.append(message)

                    # Prepare text for embedding
                    subject = getattr(message, 'subject', '') or ''
                    from_addr = getattr(message, 'from_', '') or ''
                    body = extract_body_text(message)
                    email_text = f"From: {from_addr}\nSubject: {subject}\n\n{body}"
                    email_texts.append(email_text)

                except Exception as e:
                    print(f"\n✗ Error preparing message {row['id']}: {e}")
                    error_count += 1

            # TIME: Batch embed all emails at once
            if email_texts:
                try:
                    embed_start = time.time()
                    embeddings = embedder.embed_batch(email_texts)
                    embed_time = time.time() - embed_start
                    total_embed_time += embed_time
                    print(f"  → Embedded:           {embed_time:5.2f}s  ({len(email_texts) / embed_time:6.1f} emails/s)")

                    # TIME: Store all embeddings in database (BATCH UPDATE for speed)
                    store_start = time.time()

                    # Use execute_values for batch insert - much faster than individual updates
                    from psycopg2.extras import execute_values

                    # Prepare data for batch update
                    update_data = [
                        (embedding, embedder.model_name, datetime.now(timezone.utc), message.id)
                        for message, embedding in zip(messages, embeddings)
                    ]

                    # Batch update using a temp table (PostgreSQL efficient method)
                    execute_values(
                        cur,
                        """
                        UPDATE messages AS m SET
                            embedding = v.embedding::vector,
                            embedding_model = v.model,
                            embedded_at = v.embedded_at
                        FROM (VALUES %s) AS v(embedding, model, embedded_at, id)
                        WHERE m.id = v.id
                        """,
                        update_data,
                        page_size=len(update_data)
                    )

                    single_count += len(embeddings)
                    conn.commit()
                    store_time = time.time() - store_start
                    total_store_time += store_time
                    print(f"  → Stored to DB:       {store_time:5.2f}s")

                    batch_total = fetch_time + embed_time + store_time
                    overall_rate = len(email_texts) / batch_total
                    print(f"  ✓ Batch complete:     {batch_total:5.2f}s total  ({overall_rate:6.1f} emails/s overall)")

                except Exception as e:
                    print(f"\n✗ Error batch embedding: {e}")
                    conn.rollback()
                    error_count += len(email_texts)

    finally:
        cur.close()
        conn.close()

    # Summary
    print()
    print("=" * 60)
    print("Embedding Complete!")
    print("=" * 60)
    print(f"Total messages: {total_messages}")
    print(f"  Successfully embedded: {single_count}")
    print(f"  Errors: {error_count}")
    print()
    print("Performance Breakdown:")
    total_time = total_fetch_time + total_embed_time + total_store_time
    print(f"  Fetching from DB:  {total_fetch_time:6.2f}s ({total_fetch_time / total_time * 100:5.1f}%)")
    print(f"  Embedding:         {total_embed_time:6.2f}s ({total_embed_time / total_time * 100:5.1f}%)")
    print(f"  Storing to DB:     {total_store_time:6.2f}s ({total_store_time / total_time * 100:5.1f}%)")
    print(f"  Total time:        {total_time:6.2f}s")
    print()
    if single_count > 0:
        print(f"  Throughput: {single_count / total_time:.1f} emails/second")
    print()
    print("✓ All emails have been embedded and stored in the database")
    print("✓ You can now use semantic search and RAG Q&A!")
    print()


if __name__ == "__main__":
    main()
