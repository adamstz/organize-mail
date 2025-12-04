# Agents (Runners and LLM components)

This document explains the "agents" and runtime actors in the repository — the background jobs and LLM-powered components responsible for classifying, embedding, indexing, and answering queries about emails.

Why this exists
- The codebase contains multiple *agents* (long-running or one-off scripts) that operate on email data and call LLMs. This doc helps contributors and operators understand what each agent does, where the code lives, how to run them, and how to add new agents.

Quick links
- LLM classification: `backend/src/services/llm_processor.py`
- RAG (Q&A) engine: `backend/src/services/rag_engine.py`
- Prompt templates: `backend/src/services/prompt_templates.py`
- Background job scripts: `backend/src/jobs/` (classify_all.py, embed_all_emails.py, pull_messages.py, etc.)
- Entry points / CLI: `backend/cli.py`

Contents
- Overview
- Agent types and responsibilities
- How to run (local, Docker)
- Environment variables and configuration
- Adding a new agent (developer guide)
- Observability, testing and safety
- Troubleshooting & FAQ

---

## Overview

The project organizes email processing into a few runtime actors:

1. Background jobs - single-run or scheduled scripts that fetch messages, generate embeddings, and classify messages using LLMs.
2. LLM Processors - reusable service classes that abstract calling an LLM provider (OpenAI, Anthropic, Ollama, or an external command) and parsing responses.  See `backend/src/services/llm_processor.py`.
3. RAG Engine - retrieval + generation flow for question-answering over emails. See `backend/src/services/rag_engine.py`.

Notes about the codebase and authoritative source
- Several README files are out-of-date. Prefer reading the actual code in `backend/src/` to understand current behaviour (especially LLM and RAG implementations).

---

## Agent types & responsibilities

### 1) Background jobs (workers)
Location: `backend/src/jobs/`

- `pull_messages.py` / `pull_all_inbox.py` — fetch messages from Gmail API, store them into DB. These scripts are responsible for ingestion.
- `embed_all_emails.py` — batch job to generate embeddings for messages (embedding service).
- `classify_messages.py` / `classify_all.py` — run the classification pipeline (uses the LLM processor).
- `register_watch.py` — register Gmail push watches (if using push notifications).

These scripts are intended to be run manually, by cron, or by orchestration systems (Kubernetes CronJob, runners, etc.). They are plain Python modules you can run with `python -m src.jobs.<name>` from the `backend` directory.

### 2) LLM Processor
File: `backend/src/services/llm_processor.py`

- Abstracts support for multiple LLM providers and fallbacks:
  - Providers supported: `openai`, `anthropic`, `ollama`, `command` (external command), and `rules` (local keyword-based rules for tests).
  - Implements: detection of provider via environment variables, LangChain integrations where available, provider-specific calls, fallback flows, parsing JSON output, and normalization of classification results.
- The processor is used by the classification jobs and the RAG engine.

Key behaviours and defaults (verify in code):
- Default temperature: 0.3
- Default max tokens: 200
- TIMEOUT: 60s (increased for local/slow models)
- Output parsing: accepts JSON returned in plain text or inside markdown code fences

### 3) RAG Q&A Engine
File: `backend/src/services/rag_engine.py`

- Workflow: embed question → vector search → build context → call LLM to generate answer → return answer + sources.
- Detects query types (conversation, aggregation, search-by-sender, temporal filters, classification) using `is_classification_query` & LLM helper.
- Uses `ContextBuilder` and `EmbeddingService`.

---

## How to run (developer / operator quick start)
Always verify real behaviour by checking the code (configs in `llm_processor.py`, `rag_engine.py`) — the README files may be outdated.

Note: If not running in a codespace, source your environment variables from `~/export.sh` before proceeding with the commands below.

Common run patterns (from the `backend` folder):

- Classify unclassified messages (incremental):

```bash
# activate venv and run
source .venv/bin/activate
python -m src.jobs.classify_all
```

- Force re-classify all messages (useful for testing):

```bash
python -m src.jobs.classify_all --force
```

- Run the embedding job:

```bash
python -m src.jobs.embed_all_emails
```

- Fetch messages from Gmail:

```bash
python -m src.jobs.pull_messages --user <user_email>
# or
python -m src.jobs.pull_all_inbox
```

RAG Q&A endpoint (server)
- The RAG engine is part of the API server (`backend/src/api.py`) and exposed at `POST /api/query`. Start the API server to make RAG queries.

Run server / API examples

- Start the API server (two options):

```bash
# (a) Using the repo CLI helper
python -m cli run-server

# (b) Direct with uvicorn (recommended for development)
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

- Example RAG query (curl):

```bash
curl -X POST http://127.0.0.1:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What invoices did I receive last month?","top_k":5}' | jq
```

- Start a background classify job via the API's sync endpoint (runs in background manager):

```bash
curl -X POST http://127.0.0.1:8000/api/sync/classify
```

- Logs and real-time debugging:
  - `/api/logs` returns recent logs as JSON
  - Websocket at `/ws/logs` provides real-time stream for live debugging

Docker / Compose
- The repo has a `docker-compose.yml` and a `llm/Dockerfile` — the exact compose configuration may be out-of-date. Prefer to verify the project's top-level `docker-compose.yml` and `backend/Dockerfile` for accurate developer images.

---

## Environment variables and configuration

The `LLMProcessor` reads configuration from environment variables. Key variables:

- `LLM_PROVIDER` — optional; auto-detects provider when not set. Valid values include `openai`, `anthropic`, `ollama`, `command`, or `rules` (rules is a special test fallback).
- `OPENAI_API_KEY` — OpenAI key for `openai` provider
- `ANTHROPIC_API_KEY` — Anthropic key for `anthropic` provider
- `OLLAMA_HOST` — host for Ollama server (default `http://localhost:11434`)
- `ORGANIZE_MAIL_LLM_CMD` — external command to call for `command` provider
- `LLM_MODEL` — override model name (defaults vary by provider)

Other service variables (used by storage/RAG):
- DB connection details (set in the environment or storage config)
- `PGVECTOR` and `pgvector` extension — required for RAG/embedding search in Postgres

Be cautious: the repository contains a few README files that are not kept in sync with code — check `backend/src/services/llm_processor.py` and `backend/src/services/rag_engine.py` for authoritative behaviour.

Provider examples (copy/paste)

```bash
# OpenAI (preferred when using OpenAI API)
export OPENAI_API_KEY="sk_..."
export LLM_PROVIDER=openai   # optional - detection also works

# Anthropic (Claude)
export ANTHROPIC_API_KEY="anthropic_..."
export LLM_PROVIDER=anthropic

# Ollama local server
export OLLAMA_HOST="http://localhost:11434"
export LLM_PROVIDER=ollama

# External command provider: command should accept JSON on stdin with {subject, body}
# and print JSON classification to stdout. Example: ORGANIZE_MAIL_LLM_CMD="/usr/local/bin/my_llm_cli"
export ORGANIZE_MAIL_LLM_CMD="/usr/local/bin/my_llm_cli"
export LLM_PROVIDER=command

# Test / local rule-based provider (no network calls)
export LLM_PROVIDER=rules

# Optional: override the model name
export LLM_MODEL="gpt-4"  # or "claude-3-haiku" / "llama3" depending on provider
```

Notes:
- `command` provider expects the external program to accept a JSON object `{"subject":"..","body":".."}` as stdin and produce a JSON output matching the classification schema (labels, priority, summary).
- `rules` is a test-only fallback that uses keyword matching in code; it is intentionally limited and not intended for production.

---

## Add a new agent (developer guide)
If you need to add a new agent (background job or runner), follow these conventions:

1. Location: Add the script to `backend/src/jobs/`.
2. Naming: Use clear names like `do_something.py` with `#!/usr/bin/env python3` and a `main()` block.
3. CLI: Use argparse for options like `--limit`, `--force`.
4. Reuse existing services: Import `LLMProcessor`, `EmbeddingService`, etc., from `backend/src/services/`.
5. Logging, idempotency, tests: Use logging, handle errors, make scripts idempotent, add unit/integration tests.

Example skeleton (copy into `backend/src/jobs/my_agent.py`):

```python
#!/usr/bin/env python3
import argparse
from .. import storage
from ..services import LLMProcessor

def main():
    storage.init_db()
    processor = LLMProcessor()
    # Process items...

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    main()
```

Best practices: Keep agents small and focused, reuse shared services, make idempotent, add tests.

---

## Observability, testing and safety

- Logging: Jobs should produce human-readable logs. The LLMProcessor and RAG engine include `logger.info/debug` calls for major steps.
- Timeouts and retries: LLM timeouts are configured in `LLMProcessor.TIMEOUT` (default 60s). Jobs should handle exceptions and optionally retry transient problems.
- Privacy: embeddings are created locally by default (see `docs/RAG_DOC.md`). Avoid sending raw emails to external models unless intentionally configured via provider keys.
- Testing: The repo contains unit and integration tests (`backend/tests/`) — add tests for new agents and LLM flows where applicable.
  **Contributor testing expectations:**

  - Tests are required. Any change to code should include tests (unit or integration depending on the scope) that exercise the new or modified behaviour. Tests should live near the code being changed (for example under `backend/tests/unit/` or `backend/tests/integration/`).

  - Run tests locally before creating a pull request. This helps catch regressions early and avoids CI failures. From the repository root you can run the helper Makefile targets (recommended) or use pytest directly. Example Makefile targets in `backend/Makefile`:

```bash
# run lint + all tests (recommended):
make -C backend test

# run unit tests only:
make -C backend test-unit

# run only smoke tests:
make -C backend test-smoke

# run tests with coverage report:
make -C backend test-cov

# a quick watch/iteration mode (requires ptw):
make -C backend test-watch

# formatting and linting helpers you should run before pushing:
make -C backend format
make -C backend lint
```

  If you prefer raw pytest commands they work too, but the Makefile sets appropriate environment values (for example `LLM_PROVIDER=rules` for offline tests) and paths which makes running tests easier and more deterministic.

  - If you make a larger change, run the full test suite (or the relevant integration tests) and fix any regressions before opening the PR. CI runs the full test-suite and will block merges when tests fail.

  - Documentation / markdown-only changes: small changes that only update `*.md` files (documentation, architecture notes, README, `agents.md`, etc.) do not require adding tests or running the test-suite. Still ensure the change is limited to docs and doesn't modify code or configurations — if it touches code, tests are required.

---

## Troubleshooting & FAQ

- LLM not configured: Check env vars (`OPENAI_API_KEY`, etc.) or set `LLM_PROVIDER=rules` for testing.
- Ollama issues: Ensure `ollama serve` is running, set `OLLAMA_HOST`, pull models if needed.
- Database / RAG: Confirm pgvector extension and migrations; see `docs/RAG_DOC.md`.
- Timeouts: Default 60s; tune in `LLMProcessor.TIMEOUT` for slow models.

Testing: Run with `pytest -q` in `backend/`. Use `LLM_PROVIDER=rules` for unit tests. For CI, mock LLM calls.
