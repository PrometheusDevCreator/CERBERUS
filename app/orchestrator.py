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

    # Step 2: Get raw event history from the thread
    events = await get_events(pool, session_id, command.thread_id, limit=50)

    # Parse events into a unified list with speaker attribution
    raw_messages = []
    for event in events:
        if event["event_type"] == "message.created":
            payload = event["payload"]
            if isinstance(payload, dict):
                speaker = event.get("source_id", "unknown")
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
                    raw_messages.append({"speaker": speaker, "text": text})

    def build_history_for_agent(agent_id: str, raw_msgs: list) -> list:
        """Build conversation history for a specific agent.

        Each API only supports 'user' and 'assistant' roles.
        - The agent's own previous messages -> role: 'assistant'
        - Everything else (operator + other agent) -> role: 'user' with speaker label

        Messages are merged where needed to maintain valid alternation.
        """
        history = []
        for msg in raw_msgs:
            speaker = msg["speaker"]
            text = msg["text"]

            if speaker == agent_id:
                # This agent's own previous output
                role = "assistant"
                labelled_text = text
            elif speaker == "matthew":
                # Operator message
                role = "user"
                labelled_text = f"[Matthew]: {text}"
            else:
                # The other agent's message — present as user role with attribution
                speaker_label = speaker.capitalize()
                role = "user"
                labelled_text = f"[{speaker_label}]: {text}"

            # Merge consecutive same-role messages to maintain valid alternation
            if history and history[-1]["role"] == role:
                history[-1]["content"] += f"\n\n{labelled_text}"
            else:
                history.append({"role": role, "content": labelled_text})

        return history

    # Step 3: Route to agent(s)
    target = command.payload.get("target", "both")
    user_message = command.payload.get("text", "")
    sarah_response = None

    if target in ["sarah", "both"]:
        # Build Sarah's view of the conversation
        sarah_history = build_history_for_agent("sarah", raw_messages)

        # Call Sarah
        sequence = await get_next_sequence(pool, session_id)
        sarah_response = await call_sarah(user_message, sarah_history)

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

    if target in ["claude", "both"]:
        # Build Claude's view — include Sarah's response from this turn if available
        claude_raw = raw_messages.copy()
        if sarah_response:
            claude_raw.append({"speaker": "sarah", "text": sarah_response})

        claude_history = build_history_for_agent("claude", claude_raw)

        # Call Claude
        sequence = await get_next_sequence(pool, session_id)
        claude_response = await call_claude(user_message, claude_history)

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
