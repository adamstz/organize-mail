# RAG System — Embedding and Vector Database Setup

This document covers the embedding service and vector database setup for semantic search.
For the complete query processing pipeline (classification, handlers, hybrid search, LLM interactions), see [QUERY_FLOW.md](QUERY_FLOW.md).

**Status:** Production-ready components for embedding generation and vector search.

## Contents
- [Overview](#overview)
- [Quick Start](#quick-start)
- [Vector Database Setup](#vector-database-setup)
- [Embedding Service](#embedding-service)
- [API Endpoints](#api-endpoints)
- [Batch Embedding Job](#batch-embedding-job)
- [Troubleshooting](#troubleshooting)

## Overview

The system uses local embeddings and vector search for semantic email retrieval:

- **Vector Storage:** `pgvector` extension in PostgreSQL with HNSW indexes
- **Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors)
- **Privacy:** All embeddings generated locally—no external API calls
- **Chunking:** Long emails split into overlapping chunks in `email_chunks` table
- **Search:** Cosine similarity search via pgvector
- **Hybrid Search:** Combined vector + keyword search with RRF fusion (see [QUERY_FLOW.md](QUERY_FLOW.md#retrieval-pipeline-hybrid-search))

**Key Features:**
- ✅ Fast similarity search (<50ms for 20k emails)
- ✅ HNSW Start

### Prerequisites
- PostgreSQL 12+ with `pgvector` extension
- Python virtual environment with `requirements.txt` installed
- Migrations applied (see [Vector Database Setup](#vector-database-setup))

### Generate Embeddings

```bash
cd backend
source .venv/bin/activate

# Generate embeddings for all messages
python -m src.jobs.embed_all_emails

# Check embedding status
curl http://localhost:8000/api/embedding_status | jq
```

### Test Vector Search

```bash
# Find similar emails to a specific message
curl "http://localhost:8000/api/similar/<message_id>?limit=5" | jq

# Semantic query (requires LLM running)
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Show me invoices from last month","top_k":5}' | jq

# terminal 2: run test
cd backend
python examples/test_rag.py
```

## API reference
Vector Database Setup

### Migration: Add Vector Columns

**File:** `backend/src/storage/migrations/003_add_vector_columns.sql`

This migration adds:
- `embedding` column (vector(384)) to `messages` table
- `email_chunks` table for long email chunking
- HNSW indexes for fast similarity search

**Run migration:**
```bash
cd backend
python run_migration.py src/storage/migrations/003_add_vector_columns.sql
```

**Verify:**
```sql
-- Check vector column exists
SELECT embedding FROM messages WHERE embedding IS NOT NULL LIMIT 1;

-- Check email_chunks table
SELECT COUNT(*) FROM email_chunks;

-- Verify HNSW index
SELECT indexname FROM pg_indexes 
WHERE tablename = 'messages' 
  AND indexname LIKE '%embedding%';
```
Key Files

### Embedding Service
- `backend/src/services/embedding_service.py` - Embedding generation and batching
- `backend/src/jobs/embed_all_emails.py` - Batch job to embed all messages

### Storage
- `backend/src/storage/postgres_storage.py` - Vector search methods (`similarity_search()`, `hybrid_search()`)
- `backend/src/storage/migrations/003_add_vector_columns.sql` - Vector database migration
- `backend/src/storage/migrations/001_add_fulltext_search.sql` - Full-text search migration (for hybrid search)

### API
- `backend/src/api.py` - Endpoints: `/api/embedding_status`, `/api/query`, `/api/similar/{message_id}`

### Query Pipeline
- `backend/src/services/rag_engine.py` - Orchestrates query processing
- `backend/src/services/query_handlers/semantic.py` - Semantic search handler with hybrid search and reranking

See [QUERY_FLOW.md](QUERY_FLOW.md) for complete pipeline documentation.
# Store in database
for msg, embedding in zip(messages, embeddings):
    storage.save_message_embedding(msg.id, embedding)
```

## Batch Embedding Job

**File:** `backend/src/jobs/embed_all_emails.py`

Generate embeddings for all messages in the database:

```bash
cd backend
python -m src.jobs.embed_all_emails
```

**What it does:**
1. Fetches all messages without embeddings
2. Extracts full email body text
3. Generates embeddings in batches
4. Stores embeddings in `messages.embedding` column
5. Creates chunks for long emails in `email_chunks` table

**Progress tracking:**
```
Processing batch 1/10 (100 messages)
Generated 100 embeddings in 2.3s
Saved to database
```

## API Endpoints

### GET /api/embedding_status

Returns embedding coverage statistics.

**Response:**
```json
{
  "total_messages": 5000,
  "embedded_messages": 4850,
  "coverage_percent": 97.0,
  "total_chunks": 1250
}
```

### POST /api/query

Semantic search with LLM answer generation. See [QUERY_FLOW.md](QUERY_FLOW.md) for complete query pipeline.

**Request:**
```json
{
  "question": "Show me invoices from last month",
  "top_k": 5,
  "similarity_threshold": 0.3
}
```

**Response:**
```json
{
  "answer": "Based on the emails...",
  "sources": [
    {
      "message_id": "...",
      "subject": "Invoice #1234",
      "similarity": 0.85
    }
  ],
  "query_type": "semantic",
  "confidence": "high"
}
```

### GET /api/similar/{message_id}

Find similar emails to a given message.

**Request:**
```bash
curl "http://localhost:8000/api/similar/msg123?limit=10"
```

**Response:**
```json
[
  {
    "message_id": "msg456",
    "subject": "Similar email",
    "similarity": 0.92,
    "from": "sender@example.com"
  }
]

## Files and migrations

Key project files added or updated for RAG functionality:

```
backend/
├─ src/
│  ├─ embedding_service.py      # Embedding generation and batching
│  ├─ rag_engine.py             # Retrieval and context construction
│  ├─ api.py                    # API endpoints for RAG and similarity
│  ├─ jobs/embed_all_emails.py  # Batch embedding job for all messages
│  └─ storage/
│     ├─ postgres_storage.py    # similarity_search() and vector helpers
│     └─ migrations/
│        └─ 003_add_vector_columns.sql
└─ requirements.txt             # includes sentence-transformers, pgvector

backend/examples/test_rag.py    # End-to-end test for embeddings and search
```

Database migration:

- `003_add_vector_columns.sql` — adds vector columns and `email_chunks` table.

## Architecture

High-level flow:

1. EmbeddingService converts text (messages or queries) into 384-dim vectors.
2. Vectors are stored in PostgreSQL (messages table + `email_chunks`) and
    indexed with HNSW via `pgvector`.
3. A query is embedded and used to retrieve top-k similar messages/chunks.
4. The RAG engine assembles context and calls an LLM for final answer.

Diagram (conceptual):

User → EmbeddingService → Postgres (pgvector + HNSW) → RAG Engine → LLM → User

## Troubleshooting

- If the Q&A endpoint returns an error or times out, ensure an LLM is
   available (e.g. `ollama serve`) and the configured model is present
   (`ollama pull gemma:2b`).
- If embeddings are missing, re-run the batch job:

```bash
cd backend
python src/jobs/embed_all_emails.py
```

- To inspect vector counts and sample search results, run the SQL queries in
   `examples/test_rag.py` or use psql to query `email_chunks` and `messages`.

## Notes

- Embeddings are created locally to preserve privacy; no external APIs are
   required for embedding generation.
- Vector index performance depends on HNSW parameters and dataset size; the
### Embeddings Not Generated

**Check embedding status:**
```bash
curl http://localhost:8000/api/embedding_status | jq
```

**Re-run batch job:**
```bash
cd backend
python -m src.jobs.embed_all_emails
```

**Verify embeddings in database:**
```sql
SELECT COUNT(*) FROM messages WHERE embedding IS NOT NULL;
SELECT AVG(array_length(embedding::text::float[], 1)) FROM messages WHERE embedding IS NOT NULL;
-- Should return 384 (embedding dimension)
```

### Vector Search Returns No Results

**Check if vector column exists:**
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'messages' AND column_name = 'embedding';
```

**Run migration if missing:**
```bash
python run_migration.py src/storage/migrations/003_add_vector_columns.sql
```

**Verify HNSW index:**
```sql
SELECT indexname FROM pg_indexes 
WHERE tablename = 'messages' AND indexname LIKE '%embedding%';
```

### Poor Search Quality

1. **Try hybrid search** - Combines vector + keyword search for better recall
   - Ensure full-text search migration is run: `001_add_fulltext_search.sql`
   - See [QUERY_FLOW.md](QUERY_FLOW.md#retrieval-pipeline-hybrid-search)

2. **Adjust similarity threshold** - Lower threshold to get more results
   ```python
   results = storage.similarity_search(embedding, limit=10, threshold=0.2)
   ```

3. **Check embedding quality** - Ensure full email bodies are embedded, not just snippets
   ```python
   # Use full body text
   text = message.get_body_text()  # Not message.snippet
   embedding = embedder.embed_query(text)
   ```

### Performance Issues

**Slow similarity search:**
- Verify HNSW index exists (see above)
- Tune HNSW parameters in migration if needed
- Current config optimized for ~20k emails

**Memory usage:**
- Embedding model loads ~100MB into memory
- Batch embedding processes 100 messages at a time
- Adjust batch size in `embed_all_emails.py` if needed

## Additional Resources

- **Query Pipeline:** [QUERY_FLOW.md](QUERY_FLOW.md) - Complete query processing flow
- **Database Schema:** [STORAGE_SCHEMA.md](STORAGE_SCHEMA.md) - Full schema documentation
- **Background Jobs:** [../agents.md](../agents.md) - LLM processors and batch jobs

---

**Note:** Embeddings are generated locally to preserve privacy. No external APIs are required for embedding generation.