# organize-mail

AI-powered email organization system with intelligent classification and multi-provider LLM support.

## Features

- **Email Classification**: Automatically categorize emails by type (finance, security, meetings, etc.) and priority
- **Multi-Provider LLM Support**: Choose from OpenAI, Anthropic, Ollama (local), custom commands, or rule-based classification
- **Gmail Integration**: Pull messages via Gmail API with Pub/Sub webhook support
- **Persistent Storage**: SQLite-based storage with classification history and audit trails
- **REST API**: FastAPI backend with endpoints for messages and classification
- **Modern Frontend**: React + TypeScript UI with Material-UI components

## Quick Start

### 1. Install Ollama (Recommended - Free & Private)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve &

# Pull a model (gemma:2b recommended for 8GB systems)
ollama pull gemma:2b
```

### 2. Setup Backend

```bash
cd backend
pip install -r requirements.txt

# Run classification on stored messages
PYTHONPATH=. LLM_MODEL=gemma:2b python -m src.jobs.classify_messages --limit 10

# Start API server
uvicorn src.api:app --reload
```

### 3. Setup Frontend

```bash
cd frontend
npm install
npm run dev
```

## LLM Provider Options

The system supports multiple LLM providers with automatic detection:

| Provider | Setup | Cost | Privacy | Best For |
|----------|-------|------|---------|----------|
| **Ollama** | Install locally | Free | 100% private | Production, privacy-sensitive |
| **OpenAI** | API key | ~$0.0005/email | Cloud | Best quality, high volume |
| **Anthropic** | API key | ~$0.001/email | Cloud | Claude models |
| **Rules** | None | Free | 100% private | Testing, development |
| **Command** | Custom script | Varies | Varies | Custom integrations |

### Configuration

```bash
# Auto-detect (checks Ollama → API keys → falls back to rules)
python -m src.jobs.classify_messages

# Or force a specific provider
export LLM_PROVIDER=ollama
export LLM_MODEL=gemma:2b

# OpenAI
export LLM_PROVIDER=openai
export OPENAI_API_KEY="sk-..."

# Anthropic
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

See [backend/examples/README.md](backend/examples/README.md) for detailed provider documentation.

## Project Structure

```
organize-mail/
├── backend/                 # Python FastAPI backend
│   ├── src/
│   │   ├── api.py          # REST API endpoints
│   │   ├── llm_processor.py # Multi-provider LLM system
│   │   ├── clients/        # Gmail API client
│   │   ├── jobs/           # Background jobs (classification, sync)
│   │   ├── models/         # Data models (Message, ClassificationRecord)
│   │   └── storage/        # SQLite storage layer
│   ├── tests/              # Pytest test suite
│   └── examples/           # LLM provider examples & docs
├── frontend/               # React + TypeScript UI
│   ├── src/
│   │   ├── components/     # React components (EmailList, etc.)
│   │   └── types/          # TypeScript type definitions
│   └── tests/              # Vitest test suite
├── llm/                    # Local LLM deployment (Ollama configs)
└── docs/                   # Architecture & runbooks
```

## Classification System

The LLM processor analyzes email subject and body to extract:

- **Labels**: Categories like `finance`, `security`, `meetings`, `personal`, `work`, `shopping`, etc.
- **Priority**: `high` (urgent), `normal` (routine), or `low` (can wait)

Each classification creates a `ClassificationRecord` for audit history:

```python
{
    "id": "cls-msg123-2025-11-05T12:34:56Z",
    "message_id": "msg123",
    "labels": ["finance", "work"],
    "priority": "high",
    "model": "gemma:2b",
    "created_at": "2025-11-05T12:34:56Z"
}
```

## Storage

- **Messages**: Email metadata (subject, sender, date, labels, priority)
- **Classification Records**: Audit trail of all classification runs with model info

SQLite database with migration support. In-memory mode available for testing.

## API Endpoints

```bash
# Get all messages
GET /messages

# Get a specific message
GET /messages/{message_id}

# Get classification history for a message
GET /messages/{message_id}/classifications
```

## Development

### Run Tests

```bash
# Backend tests
cd backend
PYTHONPATH=. pytest tests/ --cov=src/

# Frontend tests
cd frontend
npm test
npm run lint
```

### CI/CD

GitHub Actions workflow runs tests on push:
- Backend: pytest with coverage
- Frontend: ESLint + Vitest

## Resource Requirements

**Minimum (8GB RAM, 2 cores)**:
- Use Ollama with `gemma:2b` model (~1.7GB)
- See [backend/examples/SETUP_8GB.md](backend/examples/SETUP_8GB.md)

**Recommended (16GB+ RAM)**:
- Use Ollama with `llama3` or `mistral` models
- Or use cloud APIs (OpenAI/Anthropic) for zero local resource usage

## Documentation

- [Backend README](backend/README.md) - API, jobs, and storage details
- [Frontend README](frontend/README.md) - UI components and development
- [LLM Examples](backend/examples/README.md) - Provider setup and usage
- [Quick Reference](backend/examples/QUICKSTART.md) - One-line setup commands
- [8GB Setup Guide](backend/examples/SETUP_8GB.md) - Optimized for small VMs
- [Architecture](docs/architecture.md) - System design and data flow

## License

See [LICENSE](LICENSE)
