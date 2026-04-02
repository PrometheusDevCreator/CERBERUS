from datetime import datetime, timezone
from ulid import ULID
import asyncpg
from typing import Optional
from app.models import ClientCommand, EventEnvelope, Source, Target
from app.db import insert_event, get_events, get_next_sequence
from app.agents import call_sarah, call_claude
from app.ws_manager import ConnectionManager


def create_event_envelope(
    session_id: str,
    thread_id: str,
    event_type: str,
    source: Source,
    target: Optional[Target],
    status: str,
    payload: dict,
    sequence: int,
    visibility: str = "thread",
) -> EventEnvelope:
    """Create an EventEnvelope with standard format."""
    event_id = f"evt_{ULID()}"
    timestamp = datetime.now(timezone.utc).isoformat()

    return EventEnvelope(
        event_id=event_id,
        session_id=session_id,
        thread_id=thread_id,
        event_type=event_type,
        source=source,
        target=target,
        timestamp=timestamp,
        sequence=sequence,
        status=status,
        visibility=visibility,
        payload=payload,
        artifacts=[],
        meta={},
    )


async def handle_command(
    command: ClientCommand,
    session_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
):
    """Handle incoming client command and orchestrate agent responses."""

    # Step 1: Create and persist operator's message event
    sequence = await get_next_sequence(pool, session_id)
    operator_event = create_event_envelope(
        session_id=session_id,
        thread_id=command.thread_id,
        event_type="message.created",
        source=Source(kind="user", id="matthew", label="Matthew"),
        target=None,
        status="completed",
        payload={
            "message_id": f"msg_{ULID()}",
            "role": "user",
            "content": [{"type": "text", "text": command.payload.get("text", "")}],
            "summary": command.payload.get("text", ""),
        },
        sequence=sequence,
    )

    await insert_event(
        pool,
        operator_event.event_id,
        operator_event.session_id,
        operator_event.thread_id,
        operator_event.event_type,
        operator_event.source.kind,
        operator_event.source.id,
        operator_event.source.label,
        None,
        None,
        None,
        operator_event.timestamp,
        operator_event.sequence,
        operator_event.status,
        operator_event.visibility,
        operator_event.payload,
        operator_event.artifacts,
        operator_event.meta,
    )

    # Broadcast operator message
    await ws_manager.broadcast(session_id, operator_event.dict())

    # Step 2: Get conversation history
    events = await get_events(pool, session_id, command.thread_id, limit=50)
    conversation_history = []
    for event in events:
        if event["event_type"] == "message.created":
            payload = event["payload"]
            if isinstance(payload, dict):
                role = payload.get("role", "user")
                content = payload.get("content", [])
                text = ""
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict):
                        text = content[0].get("text", "")
                    else:
                        text = str(content[0])
                elif isinstance(content, str):
                    text = content
                if text:
                    conversation_history.append({"role": role, "content": text})

    # Step 3: Route to agent(s)
    target = command.payload.get("target", "both")
    user_message = command.payload.get("text", "")

    if target in ["sarah", "both"]:
        # Call Sarah
        sequence = await get_next_sequence(pool, session_id)
        sarah_response = await call_sarah(user_message, conversation_history)

        sarah_event = create_event_envelope(
            session_id=session_id,
            thread_id=command.thread_id,
            event_type="message.created",
            source=Source(kind="agent", id="sarah", label="Sarah"),
            target=Target(kind="user", id="matthew", label="Matthew"),
            status="completed",
            payload={
                "message_id": f"msg_{ULID()}",
                "role": "assistant",
                "content": [{"type": "text", "text": sarah_response}],
                "summary": sarah_response[:100] + "..." if len(sarah_response) > 100 else sarah_response,
            },
            sequence=sequence,
        )

        await insert_event(
            pool,
            sarah_event.event_id,
            sarah_event.session_id,
            sarah_event.thread_id,
            sarah_event.event_type,
            sarah_event.source.kind,
            sarah_event.source.id,
            sarah_event.source.label,
            sarah_event.target.kind if sarah_event.target else None,
            sarah_event.target.id if sarah_event.target else None,
            sarah_event.target.label if sarah_event.target else None,
            sarah_event.timestamp,
            sarah_event.sequence,
            sarah_event.status,
            sarah_event.visibility,
            sarah_event.payload,
            sarah_event.artifacts,
            sarah_event.meta,
        )

        await ws_manager.broadcast(session_id, sarah_event.dict())

        # Update conversation history for next agent
        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": sarah_response})

    if target in ["claude", "both"]:
        # Call Claude
        sequence = await get_next_sequence(pool, session_id)
        claude_response = await call_claude(user_message, conversation_history)

        claude_event = create_event_envelope(
            session_id=session_id,
            thread_id=command.thread_id,
            event_type="message.created",
            source=Source(kind="agent", id="claude", label="Claude"),
            target=Target(kind="user", id="matthew", label="Matthew"),
            status="completed",
            payload={
                "message_id": f"msg_{ULID()}",
                "role": "assistant",
                "content": [{"type": "text", "text": claude_response}],
                "summary": claude_response[:100] + "..." if len(claude_response) > 100 else claude_response,
            },
            sequence=sequence,
        )

        await insert_event(
            pool,
            claude_event.event_id,
            claude_event.session_id,
            claude_event.thread_id,
            claude_event.event_type,
            claude_event.source.kind,
            claude_event.source.id,
            claude_event.source.label,
            claude_event.target.kind if claude_event.target else None,
            claude_event.target.id if claude_event.target else None,
            claude_event.target.label if claude_event.target else None,
            claude_event.timestamp,
            claude_event.sequence,
            claude_event.status,
            claude_event.visibility,
            claude_event.payload,
            claude_event.artifacts,
            claude_event.meta,
        )

        await ws_manager.broadcast(session_id, claude_event.dict())
