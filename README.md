# organize-mail

AI-powered email organization system with intelligent classification and multi-provider LLM support.

## Features

- **Email Classification**: Automatically categorize emails by type (finance, security, meetings, etc.) and priority
- **Multi-Provider LLM Support**: Choose from OpenAI, Anthropic, Ollama (local), custom commands, or rule-based classification
- **Gmail Integration**: Pull messages via Gmail API with Pub/Sub webhook support
- **Flexible Storage**: SQLite or PostgreSQL backend with classification history and audit trails
- **REST API**: FastAPI backend with endpoints for messages and classification
- **Modern Frontend**: React + TypeScript UI with Material-UI components

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
│   │   └── storage/        # Storage layer (SQLite, PostgreSQL)
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

## Documentation

- [Backend README](backend/README.md) - API, jobs, and storage details
- [Frontend README](frontend/README.md) - UI components and development
- [LLM Examples](backend/examples/README.md) - Provider setup and usage
- [Quick Reference](backend/examples/QUICKSTART.md) - One-line setup commands
- [8GB Setup Guide](backend/examples/SETUP_8GB.md) - Optimized for small VMs
- [PostgreSQL Setup](POSTGRES_SETUP.md) - PostgreSQL storage configuration
- [Architecture](docs/architecture.md) - System design and data flow

## License

See [LICENSE](LICENSE)
