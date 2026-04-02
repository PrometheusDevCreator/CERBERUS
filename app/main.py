from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncpg
from ulid import ULID
from datetime import datetime
import os
import json

from app.config import settings
from app.db import init_db, get_events, create_session, get_session
from app.ws_manager import ConnectionManager
from app.models import ClientCommand, CreateSessionRequest, SessionResponse
from app.orchestrator import handle_command

app = FastAPI(title="CERBERUS", version="0.1.0")

# Global state
db_pool: asyncpg.Pool = None
ws_manager = ConnectionManager()


@app.on_event("startup")
async def startup():
    """Initialize database connection pool on startup."""
    global db_pool
    db_pool = await init_db()
    print("Database initialized")


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool on shutdown."""
    if db_pool:
        await db_pool.close()
    print("Database connection closed")


@app.get("/")
async def get_index():
    """Serve the HTML frontend."""
    return FileResponse("static/index.html", media_type="text/html")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/sessions")
async def create_new_session(request: CreateSessionRequest) -> SessionResponse:
    """Create a new session."""
    session_id = f"ses_{ULID()}"
    user_id = request.user_id or "matthew"
    user_label = request.user_label or "Matthew"

    await create_session(db_pool, session_id, user_id, user_label)

    return SessionResponse(
        session_id=session_id,
        user_id=user_id,
        created_at=datetime.utcnow(),
    )


@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str, thread_id: str = None, limit: int = 100):
    """Fetch events for a session."""
    events = await get_events(db_pool, session_id, thread_id, limit)

    # Convert jsonb fields to proper dicts
    for event in events:
        if isinstance(event["payload"], str):
            event["payload"] = json.loads(event["payload"])
        if isinstance(event["artifacts"], str):
            event["artifacts"] = json.loads(event["artifacts"])
        if isinstance(event["meta"], str):
            event["meta"] = json.loads(event["meta"])

    return {"events": events}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time message streaming."""
    await ws_manager.connect(websocket, session_id)

    try:
        while True:
            # Receive command from client
            data = await websocket.receive_text()
            command_data = json.loads(data)

            # Parse as ClientCommand
            command = ClientCommand(**command_data)

            # Ensure session exists
            session = await get_session(db_pool, session_id)
            if not session:
                await create_session(db_pool, session_id, "matthew", "Matthew")

            # Handle the command
            await handle_command(command, session_id, db_pool, ws_manager)

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, session_id)
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        await ws_manager.disconnect(websocket, session_id)


# Mount static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
