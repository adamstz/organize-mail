# Organize Mail - Backend

FastAPI backend for ingesting, storing, classifying, and searching email. Supports RAG (retrieval-augmented generation) workflows via local embeddings and pluggable LLM providers.

## Features

- **REST API**: Comprehensive endpoints for email management, classification, and RAG queries
- **WebSocket Logging**: Real-time log streaming for monitoring system activity
- **RAG Engine**: Semantic search and conversational interface powered by embeddings
- **Multi-Provider LLM**: Support for OpenAI, Anthropic, Ollama (local), custom commands, and rule-based classification
- **Gmail Integration**: Batch sync via Gmail API with refresh token authentication
- **Flexible Storage**: SQLite (development) or PostgreSQL (production) with full migration support
- **Background Jobs**: Classification, embedding generation, and message syncing
- **Ollama Management**: API endpoints to detect and start local Ollama service

## Architecture

```
backend/
├── src/
│   ├── api.py                    # Main FastAPI app with REST + WebSocket endpoints
│   ├── clients/
│   │   └── gmail_client.py       # Gmail API integration
│   ├── jobs/
│   │   ├── classify_all.py       # Batch classification
│   │   ├── embed_all_emails.py   # Batch embedding generation
│   │   └── pull_messages.py      # Gmail message sync
│   ├── models/
│   │   ├── message.py            # Email message model
│   │   └── classification_record.py  # Classification audit trail
│   ├── services/
│   │   ├── llm_processor.py      # Multi-provider LLM orchestration
│   │   ├── embedding_service.py  # Email embedding generation
│   │   ├── rag_engine.py         # Semantic search and RAG queries
│   │   ├── context_builder.py    # Context building for RAG
│   │   └── prompt_templates.py   # Centralized prompt templates
│   └── storage/
│       ├── storage_interface.py  # Abstract storage layer
│       ├── sqlite_storage.py     # SQLite implementation
│       └── postgres_storage.py   # PostgreSQL implementation
└── tests/                        # Pytest test suite
```

## Quick Start (local)

1. Create and activate a virtualenv:

	```bash
	python -m venv .venv
	source .venv/bin/activate
	pip install -r requirements.txt
	```

2. Initialize storage (SQLite is default):

	- For SQLite nothing else is required.
	- For Postgres: ensure `PG*` env vars are set and run migrations.

3. (Optional) Embed your emails:

	```bash
	python src/jobs/embed_all_emails.py
	```

4. Run the API (development):

	```bash
	uvicorn src.api:app --reload
	```

5. Run the tests:

	```bash
	pytest -q
	# or
	make test
	```

## Examples / Test Harnesses

- `backend/tests/test_rag.py`: end-to-end RAG checks (embedding status, semantic search,
  RAG Q&A, find-similar). Run directly to validate your local RAG setup.
- `backend/tests/test_llm_providers.py`: quick connectivity checks for Ollama / OpenAI / Anthropic.

## API Endpoints

### Email Management
- `GET /messages` - List emails with filtering and pagination
- `GET /messages/{message_id}` - Get single email details
- `GET /messages/{message_id}/body` - Get full email body
- `POST /messages/{message_id}/reclassify` - Trigger reclassification
- `GET /messages/filter/priority/{priority}` - Filter by priority
- `GET /messages/filter/label/{label}` - Filter by label
- `GET /messages/filter/classified` - Get classified messages
- `GET /messages/filter/unclassified` - Get unclassified messages
- `GET /messages/filter/advanced` - Advanced filtering

### Classification
- `GET /stats` - Classification statistics by label and priority
- `GET /labels` - Available classification labels

### RAG (Retrieval-Augmented Generation)
- `POST /api/query` - Ask questions about email history

### System
- `GET /models` - List available LLM models
- `GET /api/embedding_status` - Check embedding generation progress
- `POST /api/ollama/start` - Start local Ollama service
- `GET /api/sync-status` - Get sync status
- `POST /api/sync/pull` - Pull new messages
- `POST /api/sync/classify` - Classify unclassified messages
- `GET /ws/logs` - WebSocket endpoint for real-time log streaming
- `POST /api/frontend-log` - Receive logs from frontend

## LLM Providers

Supported providers: Ollama (local), OpenAI, Anthropic. Provider selection is
configured via environment variables or the settings module.

## Gmail Integration

Currently uses **batch sync** with a refresh token:
1. Generate refresh token from Google OAuth Playground
2. Set `GMAIL_USER_EMAIL` and `GMAIL_REFRESH_TOKEN` environment variables
3. Run `python src/jobs/pull_messages.py` to sync emails

**TODO**: Migrate to proper OAuth flow with Pub/Sub webhooks for real-time notifications.

## Testing

```bash
# Run all tests
pytest -q

# Run specific test files
pytest tests/test_rag.py -v          # RAG system validation
pytest tests/test_llm_providers.py   # LLM connectivity checks
pytest tests/test_api_messages.py    # API endpoint tests

# Run with coverage
pytest --cov=src --cov-report=html
```

- Ollama (recommended for local testing):
  - Run Ollama locally and point `OLLAMA_HOST` (default `http://localhost:11434`).
  - No cloud API keys required. Fast for small local models.

- OpenAI:
  - Set `OPENAI_API_KEY`.
  - Use for higher-quality models hosted by OpenAI.

- Anthropic:
  - Set `ANTHROPIC_API_KEY`.
  - Compatible provider implementation is included.

## Storage Backends

- SQLite (default): good for development and small datasets.
- Postgres + `pgvector`: recommended for production-scale vector storage and fast similarity search.

## Notes

- If embeddings are missing, run `python src/jobs/embed_all_emails.py`.
- For Postgres ensure the `email_chunks` migration has been applied and `pgvector` is installed.


make test-cov          # Run tests with coverage
```

### Features
- **Multi-provider LLM support**: OpenAI, Anthropic, Ollama, command, rule-based
- **Smart classification**: Generates labels, priority, and summary for each email
- **Semantic search**: Vector embeddings with sentence-transformers
- **Attachment detection**: Tracks which emails have attachments (without downloading them)
- **Progress tracking**: Shows real-time progress with time estimates
- **Skip classified**: Automatically skips already-classified messages
- **Persistent storage**: Stores all data in SQLite/PostgreSQL database
- **Parallel fetching**: Multi-threaded Gmail API requests for fast syncing

