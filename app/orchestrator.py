from datetime import datetime, timezone
from ulid import ULID
import asyncpg
from typing import Optional
from app.models import ClientCommand, EventEnvelope, Source, Target
from app.db import insert_event, get_events, get_next_sequence
from app.agents import call_sarah, call_claude
from app.ws_manager import ConnectionManager

# Default number of collaboration rounds (Sarah → Claude = 1 round)
DEFAULT_COLLAB_ROUNDS = 3
MAX_COLLAB_ROUNDS = 5


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


def build_history_for_agent(agent_id: str, raw_msgs: list, fallback_user_msg: str = "") -> list:
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
            role = "assistant"
            labelled_text = text
        elif speaker == "matthew":
            role = "user"
            labelled_text = f"[Matthew]: {text}"
        else:
            speaker_label = speaker.capitalize()
            role = "user"
            labelled_text = f"[{speaker_label}]: {text}"

        # Merge consecutive same-role messages to maintain valid alternation
        if history and history[-1]["role"] == role:
            history[-1]["content"] += f"\n\n{labelled_text}"
        else:
            history.append({"role": role, "content": labelled_text})

    # Ensure history ends with a user message (required by both APIs)
    if history and history[-1]["role"] != "user":
        history.append({"role": "user", "content": f"[Matthew]: {fallback_user_msg}"})

    return history


async def call_agent_and_persist(
    agent_id: str,
    raw_messages: list,
    user_message: str,
    session_id: str,
    thread_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
) -> str:
    """Call an agent, persist the response, broadcast it, and return the text."""
    history = build_history_for_agent(agent_id, raw_messages, fallback_user_msg=user_message)

    print(f"[CERBERUS] {agent_id} history: {len(history)} messages, roles: {[m['role'] for m in history]}")

    # Call the appropriate agent
    if agent_id == "sarah":
        response_text = await call_sarah(user_message, history)
        source = Source(kind="agent", id="sarah", label="Sarah")
    else:
        response_text = await call_claude(user_message, history)
        source = Source(kind="agent", id="claude", label="Claude")

    # Create and persist the event
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
            "summary": response_text[:100] + "..." if len(response_text) > 100 else response_text,
        },
        sequence=sequence,
    )

    await insert_event(
        pool,
        event.event_id,
        event.session_id,
        event.thread_id,
        event.event_type,
        event.source.kind,
        event.source.id,
        event.source.label,
        event.target.kind if event.target else None,
        event.target.id if event.target else None,
        event.target.label if event.target else None,
        event.timestamp,
        event.sequence,
        event.status,
        event.visibility,
        event.payload,
        event.artifacts,
        event.meta,
    )

    await ws_manager.broadcast(session_id, event.dict())
    return response_text


def parse_events_to_raw_messages(events: list) -> list:
    """Parse event records into a flat list with speaker attribution."""
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
    return raw_messages


async def handle_command(
    command: ClientCommand,
    session_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
):
    """Handle incoming client command and orchestrate agent responses."""

    # Step 1: Create and persist operator's message event
    sequence = await get_next_sequence(pool, session_id)
    user_message = command.payload.get("text", "")

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
    raw_messages = parse_events_to_raw_messages(events)

    print(f"[CERBERUS] raw_messages count: {len(raw_messages)}, speakers: {[m['speaker'] for m in raw_messages]}")

    # Step 3: Route based on target and mode
    target = command.payload.get("target", "both")
    mode = command.payload.get("mode", "direct")

    # ── Single-agent routing ──
    if target == "sarah":
        await call_agent_and_persist(
            "sarah", raw_messages, user_message,
            session_id, command.thread_id, pool, ws_manager,
        )
        return

    if target == "claude":
        await call_agent_and_persist(
            "claude", raw_messages, user_message,
            session_id, command.thread_id, pool, ws_manager,
        )
        return

    # ── Both agents ──
    if mode == "collaborate":
        # Collaboration loop: agents take turns responding to each other
        rounds = min(
            int(command.payload.get("rounds", DEFAULT_COLLAB_ROUNDS)),
            MAX_COLLAB_ROUNDS,
        )
        print(f"[CERBERUS] Collaboration mode: {rounds} rounds")

        # Inject collaboration framing so agents know what's expected
        collab_frame = (
            f"[CERBERUS System]: You are now in a collaborative discussion with the other agent. "
            f"This will run for {rounds} rounds. Do not just acknowledge — work the problem. "
            f"Propose ideas, analyse, challenge, and build on what the other agent says. "
            f"Matthew is observing but will not intervene between rounds. Go."
        )
        raw_messages.append({"speaker": "matthew", "text": collab_frame})

        for round_num in range(rounds):
            print(f"[CERBERUS] Collaboration round {round_num + 1}/{rounds}")

            # Inject round marker for context (not persisted, just in-memory)
            if round_num > 0:
                round_marker = f"[CERBERUS System]: Round {round_num + 1} of {rounds}. Continue working the problem. Build on what's been said — don't repeat."
                raw_messages.append({"speaker": "matthew", "text": round_marker})

            # Sarah's turn
            sarah_response = await call_agent_and_persist(
                "sarah", raw_messages, user_message,
                session_id, command.thread_id, pool, ws_manager,
            )
            raw_messages.append({"speaker": "sarah", "text": sarah_response})

            # Claude's turn
            claude_response = await call_agent_and_persist(
                "claude", raw_messages, user_message,
                session_id, command.thread_id, pool, ws_manager,
            )
            raw_messages.append({"speaker": "claude", "text": claude_response})

    else:
        # Standard "both" mode: Sarah first, then Claude (1 response each)
        sarah_response = await call_agent_and_persist(
            "sarah", raw_messages, user_message,
            session_id, command.thread_id, pool, ws_manager,
        )
        raw_messages.append({"speaker": "sarah", "text": sarah_response})

        await call_agent_and_persist(
            "claude", raw_messages, user_message,
            session_id, command.thread_id, pool, ws_manager,
        )
