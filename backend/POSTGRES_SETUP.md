# PostgreSQL Storage Setup

The application now supports PostgreSQL as a storage backend alongside SQLite.

## Quick Start

### 1. Start the CloudFlare Tunnel (Background)

```bash
# Set your environment variables
export CLOUDFLARE_ACCESS_URL="https://db.example.com"
export POSTGRES_USER="devuser"
export POSTGRES_PASSWORD="your_password"
export POSTGRES_DB="mail_db"

# Start tunnel in background (it won't hang your terminal)
./cloudflared_postgres.sh

# Check tunnel status
./cloudflared_postgres.sh status

# Stop tunnel when done
./cloudflared_postgres.sh stop
```

### 2. Use PostgreSQL with Classification

Once the tunnel is running, just set these environment variables before running any command:

```bash
# Configure PostgreSQL storage
export STORAGE_BACKEND=postgres
export DATABASE_URL="postgresql://devuser:${POSTGRES_PASSWORD}@localhost:5433/mail_db"

# Now run classification normally - it will use PostgreSQL!
cd backend
make classify

# Or force re-classify all
make classify-force
```

### 3. Pull Messages from Gmail

```bash
# Same environment variables as above
export STORAGE_BACKEND=postgres
export DATABASE_URL="postgresql://devuser:${POSTGRES_PASSWORD}@localhost:5433/mail_db"

cd backend
make pull-inbox
```

## How It Works

The application automatically selects the storage backend based on the `STORAGE_BACKEND` environment variable:

- **`sqlite`** (default) - Uses local SQLite database
- **`postgres`** - Uses PostgreSQL database
- **`memory`** - Uses in-memory storage (for testing)

When `STORAGE_BACKEND=postgres`, the application reads the connection details from:
1. `DATABASE_URL` (full connection string), or
2. Individual `POSTGRES_*` environment variables

## Tunnel Management

The `cloudflared_postgres.sh` script now runs as a daemon:

```bash
./cloudflared_postgres.sh         # Start in background
./cloudflared_postgres.sh status  # Check if running
./cloudflared_postgres.sh stop    # Stop the tunnel
./cloudflared_postgres.sh restart # Restart the tunnel
```

Logs are saved to `/tmp/cloudflared_postgres.log`.

## Testing PostgreSQL Storage

Run the comprehensive PostgreSQL storage tests:

```bash
cd backend
export TEST_DATABASE_URL="postgresql://devuser:${POSTGRES_PASSWORD}@localhost:5433/test_mail_db"
export PYTHONPATH=/workspaces/organize-mail/backend
../.venv/bin/python -m pytest tests/test_postgres_storage.py -v
```

## Switching Between SQLite and PostgreSQL

No code changes needed! Just set/unset the environment variable:

```bash
# Use SQLite (default)
unset STORAGE_BACKEND
make classify

# Use PostgreSQL
export STORAGE_BACKEND=postgres
export DATABASE_URL="postgresql://devuser:${POSTGRES_PASSWORD}@localhost:5433/mail_db"
make classify
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORAGE_BACKEND` | No | `sqlite` | Storage backend: `sqlite`, `postgres`, or `memory` |
| `DATABASE_URL` | If using postgres | - | Full PostgreSQL connection string |
| `POSTGRES_USER` | If no DATABASE_URL | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | If no DATABASE_URL | - | PostgreSQL password |
| `POSTGRES_HOST` | If no DATABASE_URL | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | If no DATABASE_URL | `5432` | PostgreSQL port |
| `POSTGRES_DB` | If no DATABASE_URL | `mail_db` | PostgreSQL database name |
| `CLOUDFLARE_ACCESS_URL` | For tunnel | - | Cloudflare Access URL for database |
