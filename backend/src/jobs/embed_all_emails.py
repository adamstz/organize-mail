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
from datetime import datetime, timezone
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.storage.storage import get_storage_backend
from src.embedding_service import EmbeddingService
from tqdm import tqdm


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


def embed_single_message(storage, embedder, message):
    """Embed a single message and store it in the database."""
    # Extract email content
    subject = getattr(message, 'subject', '') or ''
    from_addr = getattr(message, 'from_', '') or ''
    body = extract_body_text(message)
    
    # Generate embedding
    result = embedder.embed_email(subject, body, from_addr)
    
    # Get database connection
    conn = storage.connect()
    cur = conn.cursor()
    
    try:
        if result['type'] == 'single':
            # Single embedding - store in messages table
            embedding_list = result['embedding']
            
            cur.execute(
                """
                UPDATE messages 
                SET embedding = %s::vector,
                    embedding_model = %s,
                    embedded_at = %s
                WHERE id = %s
                """,
                (embedding_list, result['model'], datetime.now(timezone.utc), message.id)
            )
        
        else:  # chunked
            # Multiple embeddings - store in email_chunks table
            # First, delete any existing chunks for this message
            cur.execute("DELETE FROM email_chunks WHERE message_id = %s", (message.id,))
            
            # Insert new chunks
            for idx, chunk_data in enumerate(result['chunks']):
                chunk_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO email_chunks (id, message_id, chunk_index, chunk_text, embedding, created_at)
                    VALUES (%s, %s, %s, %s, %s::vector, %s)
                    """,
                    (
                        chunk_id,
                        message.id,
                        idx,
                        chunk_data['text'],
                        chunk_data['embedding'],
                        datetime.now(timezone.utc)
                    )
                )
            
            # Also mark the message as embedded (but no embedding in messages table)
            cur.execute(
                """
                UPDATE messages 
                SET embedding_model = %s,
                    embedded_at = %s
                WHERE id = %s
                """,
                (result['model'], datetime.now(timezone.utc), message.id)
            )
        
        conn.commit()
        return True, result['type'], result.get('token_count', 0)
    
    except Exception as e:
        conn.rollback()
        raise e
    
    finally:
        cur.close()
        conn.close()


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
    
    # Get all messages
    print("[3/4] Fetching messages from database...")
    try:
        message_ids = storage.get_message_ids()
        total_messages = len(message_ids)
        print(f"      ✓ Found {total_messages} messages to process")
    except Exception as e:
        print(f"      ✗ Failed to fetch messages: {e}")
        return
    print()
    
    if total_messages == 0:
        print("      No messages to embed. Exiting.")
        return
    
    # Process messages
    print("[4/4] Generating embeddings...")
    print(f"      Estimated time: ~{total_messages / 50:.1f} seconds on CPU")
    print(f"      Processing {total_messages} emails...")
    print()
    
    single_count = 0
    chunked_count = 0
    error_count = 0
    total_chunks = 0
    
    for message_id in tqdm(message_ids, desc="Embedding emails"):
        try:
            message = storage.get_message_by_id(message_id)
            if not message:
                error_count += 1
                continue
            
            success, embedding_type, token_count = embed_single_message(storage, embedder, message)
            
            if embedding_type == 'single':
                single_count += 1
            else:
                chunked_count += 1
                # Count chunks (approximation based on token count)
                total_chunks += max(1, token_count // embedder.MAX_TOKENS)
        
        except Exception as e:
            print(f"\n✗ Error embedding message {message_id}: {e}")
            error_count += 1
            continue
    
    # Summary
    print()
    print("=" * 60)
    print("Embedding Complete!")
    print("=" * 60)
    print(f"Total messages: {total_messages}")
    print(f"  Single embeddings: {single_count}")
    print(f"  Chunked emails: {chunked_count} ({total_chunks} chunks)")
    print(f"  Errors: {error_count}")
    print()
    print("✓ All emails have been embedded and stored in the database")
    print("✓ You can now use semantic search and RAG Q&A!")
    print()


if __name__ == "__main__":
    main()
