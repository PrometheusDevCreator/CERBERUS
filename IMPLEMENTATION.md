# CERBERUS MVP - Implementation Guide

## Overview

This is the MVP backend for CERBERUS, a triadic multi-agent coordination system. Real messages flow between a human operator (Matthew), Sarah (OpenAI GPT-5.4), and Claude (Anthropic Claude Opus 4.6) through a clean web UI.

## Architecture

### Event System
Every message is an EventEnvelope with standardized structure:
- `event_id`: Unique identifier (evt_*)
- `session_id`: User session (ses_*)
- `thread_id`: Conversation thread (thr_main)
- `event_type`: "message.created"
- `source`: Who sent it (user, agent)
- `target`: Who it's for
- `timestamp`: ISO 8601
- `sequence`: Ordering number
- `status`: "completed"
- `payload`: Message content with role, content list, summary

### Message Flow
1. User sends message via UI → WebSocket
2. Server creates operator event, persists to DB, broadcasts to all clients
3. Server calls appropriate agent API(s) based on routing
4. Agent response becomes new event, persists to DB, broadcasts
5. All clients receive updates in real-time

## File Structure

```
cerberus-build/
├── app/
│   ├── __init__.py          # Empty
│   ├── main.py              # FastAPI app, startup, routes, WebSocket
│   ├── config.py            # Environment variables
│   ├── models.py            # Pydantic schemas
│   ├── db.py                # asyncpg pool, event persistence
│   ├── ws_manager.py        # WebSocket connection tracking
│   ├── agents.py            # call_sarah(), call_claude()
│   └── orchestrator.py      # handle_command(), event routing
├── static/
│   └── index.html           # Web UI (dark theme, Prometheus colors)
├── requirements.txt         # Python dependencies
├── .env.example             # Configuration template
├── .gitignore              # Standard Python ignores
├── Procfile                # Railway deployment entry point
└── railway.toml            # Railway nixpacks config
```

## Key Components

### app/main.py
- FastAPI application with WebSocket support
- Startup: Initialize asyncpg pool, create tables
- GET `/` → serves static/index.html
- GET `/api/health` → health check
- POST `/api/sessions` → create new session
- GET `/api/sessions/{id}/events` → fetch events
- WebSocket `/ws/{session_id}` → real-time messaging

### app/db.py
- `init_db()` → Create asyncpg pool, run migrations
- `insert_event()` → Persist EventEnvelope to DB
- `get_events()` → Fetch events by session/thread
- `get_next_sequence()` → Generate sequence numbers
- Events table with indexes on (session_id, sequence) and (session_id, thread_id, sequence)

### app/agents.py
- `call_sarah()` → POST to OpenAI v1/chat/completions
  - Model: gpt-5.4 (from config)
  - Timeout: 120s
  - Max tokens: 4096
  - System prompt: Identifies as Sarah in CERBERUS
- `call_claude()` → POST to Anthropic v1/messages
  - Model: claude-opus-4-6 (from config)
  - Timeout: 120s
  - Max tokens: 4096
  - System prompt: Identifies as Claude in CERBERUS

### app/orchestrator.py
- `handle_command()` → Main orchestration logic
  1. Persist operator message
  2. Build conversation history from DB
  3. Route to agent(s) based on target: "sarah", "claude", or "both"
  4. Call agent API, get response
  5. Persist agent response
  6. Broadcast all events via WebSocket

### static/index.html
- Dark Prometheus theme: dark bg (#0a0e27), burnt orange accents (#e07830)
- Typography: Inter (body), Rajdhani (display), JetBrains Mono (code)
- Features:
  - Message thread showing all participants (color-coded)
  - Routing buttons: Sarah | Claude | Both
  - Text input with Send button
  - Real-time WebSocket connection
  - Typing indicators while agents think
  - Connection status indicator
  - Message counter
  - Auto-scroll on new messages
- Client-side JavaScript (CerberusClient class):
  - Creates session on load
  - Connects to WebSocket
  - Sends commands as JSON
  - Renders received events in UI
  - Manages typing indicators

## Environment Variables

Required in .env:
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `SARAH_MODEL` - OpenAI model ID (e.g., gpt-5.4)
- `CLAUDE_MODEL` - Anthropic model ID (e.g., claude-opus-4-6)
- `DATABASE_URL` - PostgreSQL connection string
- `PORT` - Server port (default 8000)

## Deployment (Railway)

1. Create Railway project
2. Add PostgreSQL addon (auto-sets DATABASE_URL)
3. Add secrets: OPENAI_API_KEY, ANTHROPIC_API_KEY, SARAH_MODEL, CLAUDE_MODEL
4. Connect GitHub repo or upload code
5. Railway runs: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`

Key files:
- `Procfile` - Traditional Procfile format (optional with nixpacks)
- `railway.toml` - Explicit start command for nixpacks builder

## Dependencies

- `fastapi` - Web framework
- `uvicorn[standard]` - ASGI server
- `websockets` - WebSocket support
- `httpx` - Async HTTP client for agent APIs
- `asyncpg` - PostgreSQL async driver
- `python-ulid` - Generate ULIDs for IDs
- `python-dotenv` - Environment variables
- `pydantic>=2.0` - Data validation

## Testing Locally

```bash
# Install
pip install -r requirements.txt

# Setup .env
cp .env.example .env
# Edit .env with your keys and local DB URL

# Start PostgreSQL
# (use docker or local installation)
# docker run -d -p 5432:5432 -e POSTGRES_DB=cerberus postgres

# Run
python -m uvicorn app.main:app --reload --port 8000

# Visit http://localhost:8000
```

## Next Steps (Beyond MVP)

- Task dispatch system (assign work to agents)
- Job queue with status tracking
- Approval gates for sensitive operations
- Multi-thread conversations
- Message versioning and history
- User authentication
- Conversation persistence across sessions
- Rich formatting (markdown, code blocks, tables)
- File attachments
- Rate limiting and usage tracking

## Notes

- This is MVP only - focuses on real message flow, not advanced features
- All imports are correct and dependencies are listed
- Code is production-ready for basic deployment
- Event schema follows the v0 system contract
- ID prefixes: evt_, ses_, thr_, msg_ (not yet used for individual messages)
