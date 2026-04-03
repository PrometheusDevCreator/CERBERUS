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


def parse_events_to_raw_messages(events: list) -> list:
    """Parse DB event records into a flat list: [{speaker, text}, ...]"""
    raw = []
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
                    raw.append({"speaker": speaker, "text": text})
    return raw


def build_history_for_agent(agent_id: str, raw_msgs: list) -> list:
    """Build API-compatible conversation history for an agent.

    Rules:
    - Agent's own messages → role: assistant (no label)
    - All other messages → role: user with [Speaker]: prefix
    - Consecutive same-role messages are merged (API requirement)
    - History must end with role: user
    """
    history = []
    for msg in raw_msgs:
        speaker = msg["speaker"]
        text = msg["text"]

        if speaker == agent_id:
            role = "assistant"
            content = text
        else:
            role = "user"
            label = speaker.capitalize()
            content = f"[{label}]: {text}"

        if history and history[-1]["role"] == role:
            history[-1]["content"] += f"\n\n{content}"
        else:
            history.append({"role": role, "content": content})

    # Both APIs require the last message to be role: user
    if history and history[-1]["role"] != "user":
        # This shouldn't normally happen since Matthew's message is always last,
        # but guard against edge cases
        history.append({"role": "user", "content": "[Matthew]: Please continue."})

    return history


async def persist_and_broadcast(
    agent_id: str,
    response_text: str,
    session_id: str,
    thread_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
):
    """Persist an agent response as an event and broadcast to all clients."""
    label = agent_id.capitalize()
    source = Source(kind="agent", id=agent_id, label=label)

    sequence = await get_next_sequence(pool, session_id)
    event = create_event_envelope(
        session_id=session_id,
        thread_id=thread_id,
        event_type="message.created",
        source=source,
        target=Target(kind="user", id="matthew", label="Matthew"),
        status="completed",
        payload={
            "message_id": f"msg_{ULID()}",
            "role": "assistant",
            "content": [{"type": "text", "text": response_text}],
            "summary": response_text[:100] + ("..." if len(response_text) > 100 else ""),
        },
        sequence=sequence,
    )

    await insert_event(
        pool,
        event.event_id, event.session_id, event.thread_id,
        event.event_type, event.source.kind, event.source.id, event.source.label,
        event.target.kind if event.target else None,
        event.target.id if event.target else None,
        event.target.label if event.target else None,
        event.timestamp, event.sequence, event.status, event.visibility,
        event.payload, event.artifacts, event.meta,
    )

    await ws_manager.broadcast(session_id, event.dict())


async def call_agent(agent_id: str, history: list) -> str:
    """Call the appropriate agent API."""
    if agent_id == "sarah":
        return await call_sarah(history)
    else:
        return await call_claude(history)


async def handle_command(
    command: ClientCommand,
    session_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
):
    """Handle incoming client command."""

    user_message = command.payload.get("text", "")
    mode = command.payload.get("mode", "conference")
    target = command.payload.get("target", "sarah")  # only used in direct mode

    # ── Persist and broadcast operator's message ──
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
            "content": [{"type": "text", "text": user_message}],
            "summary": user_message,
        },
        sequence=sequence,
    )

    await insert_event(
        pool,
        operator_event.event_id, operator_event.session_id, operator_event.thread_id,
        operator_event.event_type, operator_event.source.kind,
        operator_event.source.id, operator_event.source.label,
        None, None, None,
        operator_event.timestamp, operator_event.sequence,
        operator_event.status, operator_event.visibility,
        operator_event.payload, operator_event.artifacts, operator_event.meta,
    )
    await ws_manager.broadcast(session_id, operator_event.dict())

    # ── Load conversation history ──
    events = await get_events(pool, session_id, command.thread_id, limit=50)
    raw_messages = parse_events_to_raw_messages(events)

    # ── CONFERENCE MODE ──
    # Both agents see everything. Both get a chance to respond.
    # Each agent decides for itself whether to contribute based on the message content.
    if mode == "conference":
        # Sarah responds first
        sarah_history = build_history_for_agent("sarah", raw_messages)
        sarah_response = await call_agent("sarah", sarah_history)
        await persist_and_broadcast("sarah", sarah_response, session_id, command.thread_id, pool, ws_manager)
        raw_messages.append({"speaker": "sarah", "text": sarah_response})

        # Claude responds second, seeing Sarah's reply
        claude_history = build_history_for_agent("claude", raw_messages)
        claude_response = await call_agent("claude", claude_history)
        await persist_and_broadcast("claude", claude_response, session_id, command.thread_id, pool, ws_manager)

    # ── DIRECT MODE ──
    # Only the targeted agent responds. The other agent does not see this conversation.
    # However, if the responding agent's reply contains a request to consult the other
    # agent, we call the other agent too (Matthew sees both, but only the primary
    # agent continues the conversation).
    elif mode == "direct":
        primary = target  # "sarah" or "claude"
        other = "claude" if primary == "sarah" else "sarah"

        primary_history = build_history_for_agent(primary, raw_messages)
        primary_response = await call_agent(primary, primary_history)
        await persist_and_broadcast(primary, primary_response, session_id, command.thread_id, pool, ws_manager)

        # Check if the primary agent is requesting the other agent's input
        consult_triggers = [
            f"ask {other}",
            f"bring {other} in",
            f"check with {other}",
            f"get {other}'s",
            f"@{other}",
            f"consult {other}",
            f"{other} should weigh in",
            f"{other} might",
            f"defer to {other}",
        ]
        response_lower = primary_response.lower()
        should_consult = any(trigger in response_lower for trigger in consult_triggers)

        if should_consult:
            # Build history including the primary agent's response
            raw_messages.append({"speaker": primary, "text": primary_response})
            # Frame the consultation
            consult_msg = (
                f"[{primary.capitalize()}] has suggested consulting you on this. "
                f"Here is the conversation so far. Please provide your input."
            )
            raw_messages.append({"speaker": "matthew", "text": consult_msg})

            other_history = build_history_for_agent(other, raw_messages)
            other_response = await call_agent(other, other_history)
            await persist_and_broadcast(other, other_response, session_id, command.thread_id, pool, ws_manager)
