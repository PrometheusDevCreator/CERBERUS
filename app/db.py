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

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                detail TEXT NOT NULL,
                source_session_id TEXT,
                source_event_id TEXT,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                tags JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_used_at TIMESTAMPTZ
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_scope_status
            ON memories(user_id, scope, status, updated_at DESC)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user_summary
            ON memories(user_id, LOWER(summary))
        """)

    return pool


async def insert_event_record(
    conn: asyncpg.Connection,
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
    """Insert an event using an existing connection."""
    # asyncpg requires a datetime object, not a string
    if isinstance(timestamp, str):
        ts = datetime.fromisoformat(timestamp)
    else:
        ts = timestamp

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
    async with pool.acquire() as conn:
        await insert_event_record(
            conn,
            event_id,
            session_id,
            thread_id,
            event_type,
            source_kind,
            source_id,
            source_label,
            target_kind,
            target_id,
            target_label,
            timestamp,
            sequence,
            status,
            visibility,
            payload,
            artifacts,
            meta,
            run_id,
            parent_event_id,
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
                SELECT * FROM (
                    SELECT * FROM events
                    WHERE session_id = $1 AND thread_id = $2
                    ORDER BY sequence DESC
                    LIMIT $3
                ) recent
                ORDER BY sequence ASC
                """,
                session_id,
                thread_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM (
                    SELECT * FROM events
                    WHERE session_id = $1
                    ORDER BY sequence DESC
                    LIMIT $2
                ) recent
                ORDER BY sequence ASC
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


def canonicalize_event(event: dict) -> dict:
    """Convert raw DB rows into the canonical event envelope shape."""
    payload = event.get("payload", {})
    artifacts = event.get("artifacts", [])
    meta = event.get("meta", {})

    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(artifacts, str):
        artifacts = json.loads(artifacts)
    if isinstance(meta, str):
        meta = json.loads(meta)

    target = None
    if event.get("target_kind") and event.get("target_id"):
        target = {
            "kind": event.get("target_kind"),
            "id": event.get("target_id"),
            "label": event.get("target_label"),
        }

    return {
        "event_id": event.get("event_id"),
        "session_id": event.get("session_id"),
        "thread_id": event.get("thread_id"),
        "run_id": event.get("run_id"),
        "parent_event_id": event.get("parent_event_id"),
        "event_type": event.get("event_type"),
        "source": {
            "kind": event.get("source_kind"),
            "id": event.get("source_id"),
            "label": event.get("source_label"),
        },
        "target": target,
        "timestamp": event.get("timestamp").isoformat() if isinstance(event.get("timestamp"), datetime) else event.get("timestamp"),
        "sequence": event.get("sequence"),
        "status": event.get("status"),
        "visibility": event.get("visibility"),
        "payload": payload,
        "artifacts": artifacts,
        "meta": meta,
    }


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


async def upsert_memory(
    pool: asyncpg.Pool,
    memory_id: str,
    user_id: str,
    scope: str,
    category: str,
    summary: str,
    detail: str,
    source_session_id: str,
    source_event_id: str,
    source_kind: str,
    source_id: str,
    tags: Optional[List[str]] = None,
):
    """Insert or refresh an approved cross-session memory."""
    tags = tags or []

    async with pool.acquire() as conn:
        existing_id = await conn.fetchval(
            """
            SELECT memory_id
            FROM memories
            WHERE user_id = $1
              AND scope = $2
              AND status = 'active'
              AND LOWER(summary) = LOWER($3)
            LIMIT 1
            """,
            user_id,
            scope,
            summary,
        )

        if existing_id:
            await conn.execute(
                """
                UPDATE memories
                SET category = $2,
                    detail = $3,
                    source_session_id = $4,
                    source_event_id = $5,
                    source_kind = $6,
                    source_id = $7,
                    tags = $8,
                    updated_at = NOW()
                WHERE memory_id = $1
                """,
                existing_id,
                category,
                detail,
                source_session_id,
                source_event_id,
                source_kind,
                source_id,
                json.dumps(tags),
            )
            return existing_id

        await conn.execute(
            """
            INSERT INTO memories (
                memory_id, user_id, scope, category, summary, detail,
                source_session_id, source_event_id, source_kind, source_id,
                tags
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10,
                $11
            )
            """,
            memory_id,
            user_id,
            scope,
            category,
            summary,
            detail,
            source_session_id,
            source_event_id,
            source_kind,
            source_id,
            json.dumps(tags),
        )
        return memory_id


async def get_memories(
    pool: asyncpg.Pool,
    user_id: str,
    scopes: Optional[List[str]] = None,
    limit: int = 20,
) -> List[dict]:
    """Fetch active memories for a user."""
    async with pool.acquire() as conn:
        if scopes:
            rows = await conn.fetch(
                """
                SELECT *
                FROM memories
                WHERE user_id = $1
                  AND status = 'active'
                  AND scope = ANY($2::text[])
                ORDER BY updated_at DESC
                LIMIT $3
                """,
                user_id,
                scopes,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT *
                FROM memories
                WHERE user_id = $1
                  AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )

    memories = []
    for row in rows:
        memory = dict(row)
        tags = memory.get("tags", [])
        if isinstance(tags, str):
            tags = json.loads(tags)
        memory["tags"] = tags
        memories.append(memory)
    return memories


async def mark_memories_used(pool: asyncpg.Pool, memory_ids: List[str]) -> None:
    """Track when memories were injected into a prompt."""
    if not memory_ids:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE memories
            SET last_used_at = NOW()
            WHERE memory_id = ANY($1::text[])
            """,
            memory_ids,
        )
