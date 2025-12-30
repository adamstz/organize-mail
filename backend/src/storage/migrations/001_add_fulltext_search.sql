-- Migration: Add full-text search support for hybrid search
-- This enables combining vector similarity with keyword search using PostgreSQL's tsvector

-- Add tsvector column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'messages' AND column_name = 'search_vector'
    ) THEN
        ALTER TABLE messages ADD COLUMN search_vector tsvector;
    END IF;
END $$;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_messages_search_vector_gin
ON messages USING GIN (search_vector);

-- Create function to update tsvector
CREATE OR REPLACE FUNCTION messages_search_vector_trigger() RETURNS trigger AS $$
BEGIN
    -- Weight factors: A (highest) for subject, B for snippet, C for sender
    NEW.search_vector := 
        setweight(to_tsvector('english', coalesce(NEW.subject, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.snippet, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.from_addr, '')), 'C');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- Drop existing trigger if it exists
DROP TRIGGER IF EXISTS messages_search_vector_update ON messages;

-- Create trigger to auto-update tsvector on INSERT/UPDATE
CREATE TRIGGER messages_search_vector_update
    BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW
    EXECUTE FUNCTION messages_search_vector_trigger();

-- Populate search_vector for existing messages
UPDATE messages
SET search_vector = 
    setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(snippet, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(from_addr, '')), 'C')
WHERE search_vector IS NULL;
