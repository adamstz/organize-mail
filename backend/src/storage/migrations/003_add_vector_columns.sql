-- Migration 003: Add vector columns for RAG functionality
-- This migration adds pgvector support for semantic search and RAG

-- Add vector embedding column to messages table for short emails
-- Using 384 dimensions for sentence-transformers all-MiniLM-L6-v2 model
ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS embedding vector(384),
ADD COLUMN IF NOT EXISTS embedding_model TEXT,
ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMP WITH TIME ZONE;

-- Create email_chunks table for long emails that need to be split
CREATE TABLE IF NOT EXISTS email_chunks (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(message_id, chunk_index)
);

-- Create HNSW indexes for fast approximate nearest neighbor search
-- HNSW (Hierarchical Navigable Small World) provides ~100x speedup over brute force
-- Using cosine distance (vector_cosine_ops) which is standard for text embeddings
CREATE INDEX IF NOT EXISTS idx_messages_embedding_hnsw 
ON messages USING hnsw (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_email_chunks_embedding_hnsw 
ON email_chunks USING hnsw (embedding vector_cosine_ops);

-- Index for looking up chunks by message_id
CREATE INDEX IF NOT EXISTS idx_email_chunks_message_id 
ON email_chunks(message_id);

-- Index for sorting chunks by position
CREATE INDEX IF NOT EXISTS idx_email_chunks_chunk_index 
ON email_chunks(message_id, chunk_index);

-- Add comment documentation
COMMENT ON COLUMN messages.embedding IS 'Vector embedding (384-dim) for semantic search. Only for emails <400 tokens.';
COMMENT ON COLUMN messages.embedding_model IS 'Name of the embedding model used (e.g., all-MiniLM-L6-v2)';
COMMENT ON COLUMN messages.embedded_at IS 'Timestamp when the embedding was generated';
COMMENT ON TABLE email_chunks IS 'Stores chunks of long emails (>400 tokens) with their embeddings for semantic search';
COMMENT ON COLUMN email_chunks.chunk_index IS 'Position of chunk in the email (0-based index)';
