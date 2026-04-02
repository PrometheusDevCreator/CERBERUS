import asyncpg
from datetime import datetime, timezone
from typing import Optional, List, Any
import json
from app.config import settings


async def init_db():
    """Initialize database connection pool and create tables."""
    pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=5,
        max_size=20,
    )

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                run_id TEXT,
                parent_event_id TEXT,
                event_type TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_label TEXT,
                target_kind TEXT,
                target_id TEXT,
                target_label TEXT,
                timestamp TIMESTAMPTZ NOT NULL,
                sequence BIGINT NOT NULL,
                status TEXT NOT NULL,
                visibility TEXT,
                payload JSONB NOT NULL DEFAULT '{}',
                artifacts JSONB NOT NULL DEFAULT '[]',
                meta JSONB NOT NULL DEFAULT '{}',
                UNIQUE(session_id, sequence)
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_session_sequence
            ON events(session_id, sequence)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_session_thread_sequence
            ON events(session_id, thread_id, sequence)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_event_type
            ON events(event_type)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                user_label TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id
            ON sessions(user_id)
        """)

    return pool


async def insert_event(
    pool: asyncpg.Pool,
    event_id: str,
    session_id: str,
    thread_id: str,
    event_type: str,
    source_kind: str,
    source_id: str,
    source_label: Optional[str],
    target_kind: Optional[str],
    target_id: Optional[str],
    target_label: Optional[str],
    timestamp: str,
    sequence: int,
    status: str,
    visibility: Optional[str],
    payload: dict,
    artifacts: List[Any],
    meta: dict,
    run_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
) -> None:
    """Insert an event into the database."""
    # asyncpg requires a datetime object, not a string
    if isinstance(timestamp, str):
        ts = datetime.fromisoformat(timestamp)
    else:
        ts = timestamp

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO events (
                event_id, session_id, thread_id, run_id, parent_event_id,
                event_type, source_kind, source_id, source_label,
                target_kind, target_id, target_label,
                timestamp, sequence, status, visibility,
                payload, artifacts, meta
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12,
                $13, $14, $15, $16,
                $17, $18, $19
            )
            """,
            event_id,
            session_id,
            thread_id,
            run_id,
            parent_event_id,
            event_type,
            source_kind,
            source_id,
            source_label,
            target_kind,
            target_id,
            target_label,
            ts,
            sequence,
            status,
            visibility,
            json.dumps(payload),
            json.dumps(artifacts),
            json.dumps(meta),
        )


async def get_events(
    pool: asyncpg.Pool,
    session_id: str,
    thread_id: Optional[str] = None,
    limit: int = 100,
) -> List[dict]:
    """Fetch events for a session, optionally filtered by thread."""
    async with pool.acquire() as conn:
        if thread_id:
            rows = await conn.fetch(
                """
                SELECT * FROM events
                WHERE session_id = $1 AND thread_id = $2
                ORDER BY sequence ASC
                LIMIT $3
                """,
                session_id,
                thread_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM events
                WHERE session_id = $1
                ORDER BY sequence ASC
                LIMIT $2
                """,
                session_id,
                limit,
            )

    return [dict(row) for row in rows]


async def get_next_sequence(pool: asyncpg.Pool, session_id: str) -> int:
    """Get the next sequence number for a session."""
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE session_id = $1",
            session_id,
        )
    return result


async def create_session(
    pool: asyncpg.Pool, session_id: str, user_id: str, user_label: Optional[str] = None
) -> None:
    """Create a new session."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sessions (session_id, user_id, user_label)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            session_id,
            user_id,
            user_label,
        )


async def get_session(pool: asyncpg.Pool, session_id: str) -> Optional[dict]:
    """Get session info."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sessions WHERE session_id = $1", session_id)
    return dict(row) if row else None
