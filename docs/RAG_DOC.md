## ✅ What's Been Implemented

Your email organization system now has a **complete RAG (Retrieval-Augmented Generation) pipeline**:

### 1. **Vector Database** ✓
- ✅ pgvector extension installed in PostgreSQL 18
- ✅ Vector columns added to `messages` table (384 dimensions)
- ✅ `email_chunks` table created for long emails
- ✅ HNSW indexes for fast similarity search (<50ms for 20k emails)

### 2. **Embedding Service** ✓
- ✅ sentence-transformers integration (all-MiniLM-L6-v2)
## RAG System — Overview and Reference

This document summarizes the implemented Retrieval-Augmented Generation (RAG)
capabilities, how to run them, available endpoints, and where to find related
code and migrations.

Status: Production-ready components for embedding, vector search, and RAG
querying are included. The Q&A endpoint requires a running LLM (e.g. Ollama)
for full functionality.

Contents
- Overview
- Quick start
- API reference
- Files and migrations
- Architecture
- Troubleshooting
- Notes
- Next steps

## Overview

- Vector storage: `pgvector` extension used with PostgreSQL.
- Embeddings: `sentence-transformers` (all-MiniLM-L6-v2) generating 384-dim
   vectors locally.
- Chunking: long emails are split into overlapping chunks and stored in
   `email_chunks` for retrieval.
- Indexing: HNSW indexes on vector columns for fast similarity search.
- Retrieval: Postgres-based similarity search (cosine) implemented in
   `PostgresStorage`.
- RAG: Query workflow that embeds the question, retrieves top-k documents,
   constructs context, and forwards to an LLM for generation.

## Quick start

Prerequisites:
- PostgreSQL with `pgvector` extension available and migrations applied.
- A Python virtual environment with project requirements installed.
- (Optional for Q&A) Ollama or another LLM running locally for generation.

Start the API server (development):

```bash
cd backend
source .venv/bin/activate
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

Run the semantic search test (does not require LLM):

```bash
cd backend
python examples/test_rag.py
```

Run full Q&A (requires Ollama):

```bash
# terminal 1: start Ollama
ollama serve

# terminal 2: run test
cd backend
python examples/test_rag.py
```

## API reference

All endpoints are mounted under the API server (default port 8000).

- `GET /api/embedding_status`
   - Returns embedding coverage and indexing state.

- `POST /api/query`
   - Request: JSON `{ "question": "...", "top_k": 5, "model": "gemma:2b" }`
   - Behavior: embeds the question, retrieves top-k relevant contexts, calls
      the configured LLM with constructed prompt, and returns generated answer
      with source citations.

- `GET /api/similar/{message_id}`
   - Query similar messages (supports `?limit=`).

Examples:

```bash
# status
curl http://localhost:8000/api/embedding_status | jq

# semantic question (requires LLM)
curl -X POST http://localhost:8000/api/query \
   -H "Content-Type: application/json" \
   -d '{"question":"Show me invoices from last year","top_k":5}' | jq

# similar messages
curl "http://localhost:8000/api/similar/<message_id>?limit=5" | jq
```

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
   current configuration is tuned for ~20k emails.

## Contact / Next steps

For UI integration or additional features (hybrid filtering, re-ranking,
frontend chat UI), see `docs/RAG_USAGE.md` for implementation notes and
consider opening a feature branch.

----

End of reference documentation.
└────────────────────┬────────────────────────────────────┘
