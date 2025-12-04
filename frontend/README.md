# Organize Mail - Frontend

React + TypeScript frontend for the Organize Mail application. Provides an intuitive interface for managing classified emails, chatting with your email history via RAG, and monitoring system activity in real-time.

## Features

- **Email Management**: Browse, filter, and search classified emails with pagination
- **Smart Filtering**: Filter by label (Finance, Security, Meetings, etc.), priority, and custom search queries
- **RAG-Powered Chat**: Conversational interface to ask questions about your email history
- **Real-Time Logging**: WebSocket-based log viewer with filtering, pause/resume, and export
- **Reclassification**: Manually trigger reclassification for individual emails
- **LLM Model Selection**: Choose from available models (OpenAI, Anthropic, Ollama)
- **Ollama Integration**: Automatically detect and start local Ollama service when needed
- **Responsive UI**: Material-UI components with dark theme and resizable panels

## Architecture

```
frontend/
├── src/
│   ├── components/
│   │   ├── EmailList.tsx         # Main email list with pagination
│   │   ├── EmailItem.tsx         # Individual email display
│   │   ├── EmailToolbar.tsx      # Filters, search, model selection
│   │   ├── ChatInterface.tsx     # RAG chat UI
│   │   ├── LogViewer.tsx         # Real-time log streaming
│   │   └── SyncStatus.tsx        # Sync status display
│   ├── utils/
│   │   └── logger.ts             # Frontend logging utility
│   ├── types/
│   │   └── index.ts              # TypeScript type definitions
│   ├── App.tsx                   # Root component with layout
│   └── main.tsx                  # Application entry point
├── vite.config.ts                # Vite configuration with proxies
└── public/                       # Static assets
```

## Quick Start

1. **Install dependencies**
   ```bash
   npm install
   ```

2. **Start development server**
   ```bash
   npm run dev
   ```

3. **Build for production**
   ```bash
   npm run build
   ```

4. **Run tests**
   ```bash
   npm test
   ```

## Development

The frontend uses Vite for fast development with HMR (Hot Module Replacement) and proxies API requests to the backend:

- `/api/*` → `http://localhost:8000` (REST API)
- `/ws/*` → `ws://localhost:8000` (WebSocket for logs)

### Key Components

- **EmailList**: Displays paginated emails with filtering and sorting
- **EmailToolbar**: Provides filters (label, priority), search, and model selection
- **EmailItem**: Shows individual email with metadata, classification, and reclassify button
- **ChatInterface**: RAG chat with query input, streaming responses, and source citations
- **LogViewer**: Real-time log viewer with WebSocket connection, filtering, and controls
- **SyncStatus**: Displays current sync and classification status

### Logging

The frontend includes a comprehensive logging system:
- All user actions (filters, searches, reclassifications) are logged
- Logs are sent to backend via `/api/frontend-log` endpoint
- Real-time logs viewable in LogViewer component via WebSocket

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Material-UI (MUI)** - Component library
- **WebSocket API** - Real-time log streaming

## Configuration

### Vite Proxy

The `vite.config.ts` configures proxies for backend communication:

```typescript
proxy: {
  '/api': 'http://localhost:8000',
  '/ws': {
    target: 'ws://localhost:8000',
    ws: true
  }
}
```

### Environment Variables

Create a `.env.local` file for environment-specific configuration:

```bash
VITE_API_URL=http://localhost:8000  # Optional: override API URL
```

## Production Deployment

For production, the Vite proxy is not used. Configure your reverse proxy (nginx, Caddy, etc.) to route:
- `/api/*` → Backend API server
- `/ws/*` → Backend WebSocket server (with upgrade headers)

Example nginx configuration:

```nginx
location /api/ {
    proxy_pass http://backend:8000;
}

location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```
