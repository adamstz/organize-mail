# Organize Mail - Backend

Backend for ingesting, storing, and classifying email. Supports RAG (retrieval-augmented
generation) workflows via local embeddings and pluggable LLM providers.

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

## LLM Providers (Quick Reference)

Supported providers: Ollama (local), OpenAI, Anthropic. Provider selection is
configured via environment variables or the settings module.

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

