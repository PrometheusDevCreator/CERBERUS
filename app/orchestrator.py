from datetime import datetime, timezone
import json
from typing import Optional

import asyncpg
from ulid import ULID

from app.agents import call_claude, call_sarah
from app.db import get_events, get_memories, insert_event_record, mark_memories_used, upsert_memory
from app.memory import detect_scope, extract_memory_candidate, format_memory_context, rank_memories
from app.models import ClientCommand, EventEnvelope, Source, Target
from app.ws_manager import ConnectionManager

CONFERENCE_ROUNDS = 3
RESPONSE_DISCIPLINE = (
    "[Response Discipline]: Be concise unless Matthew explicitly asks for depth. "
    "Receipts must be one short sentence. Direct replies should usually stay within 2-4 sentences. "
    "Conference discussion turns should stay within 3 short points or roughly 120 words. "
    "Final briefs should stay within 4 short lines."
)


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
    )


def parse_events_to_raw_messages(events: list) -> list:
    """Parse DB event records into speaker/text items for agent history."""
    raw = []
    for event in events:
        if event.get("event_type") != "message.created":
            continue

        payload = event.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {}

        if not isinstance(payload, dict):
            continue

        speaker = event.get("source_id") or event.get("source", {}).get("id", "unknown")
        content = payload.get("content", [])
        text = ""

        if isinstance(content, list) and content:
            first = content[0]
            text = first.get("text", "") if isinstance(first, dict) else str(first)
        elif isinstance(content, str):
            text = content

        if text:
            raw.append({"speaker": speaker, "text": text})

    return raw


def build_history_for_agent(
    agent_id: str,
    raw_msgs: list,
    guidance: Optional[str] = None,
    memory_context: Optional[str] = None,
) -> list:
    """Build API-compatible conversation history for an agent."""
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

    if memory_context:
        if history and history[-1]["role"] == "user":
            history[-1]["content"] += f"\n\n{memory_context}"
        else:
            history.append({"role": "user", "content": memory_context})

    if history and history[-1]["role"] == "user":
        history[-1]["content"] += f"\n\n{RESPONSE_DISCIPLINE}"
    else:
        history.append({"role": "user", "content": RESPONSE_DISCIPLINE})

    if guidance:
        guidance_text = f"[Conference Controller]: {guidance}"
        if history and history[-1]["role"] == "user":
            history[-1]["content"] += f"\n\n{guidance_text}"
        else:
            history.append({"role": "user", "content": guidance_text})

    if history and history[-1]["role"] != "user":
        history.append({"role": "user", "content": "[Matthew]: Please continue."})

    return history


async def persist_event(
    session_id: str,
    thread_id: str,
    event_type: str,
    source: Source,
    target: Optional[Target],
    payload: dict,
    pool: asyncpg.Pool,
    status: str = "completed",
    visibility: str = "thread",
    meta: Optional[dict] = None,
) -> EventEnvelope:
    """Persist an event with an atomically allocated session sequence."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", session_id)
            sequence = await conn.fetchval(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM events WHERE session_id = $1",
                session_id,
            )

            event = create_event_envelope(
                session_id=session_id,
                thread_id=thread_id,
                event_type=event_type,
                source=source,
                target=target,
                status=status,
                payload=payload,
                sequence=sequence,
                visibility=visibility,
            )
            event.meta = meta or {}

            await insert_event_record(
                conn,
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

    return event


async def persist_and_broadcast(
    agent_id: str,
    response_text: str,
    session_id: str,
    thread_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
    message_type: str = "response",
    meta: Optional[dict] = None,
):
    """Persist an agent response and broadcast it."""
    label = agent_id.capitalize()
    source = Source(kind="agent", id=agent_id, label=label)
    event = await persist_event(
        session_id=session_id,
        thread_id=thread_id,
        event_type="message.created",
        source=source,
        target=Target(kind="user", id="matthew", label="Matthew"),
        payload={
            "message_id": f"msg_{ULID()}",
            "role": "assistant",
            "content": [{"type": "text", "text": response_text}],
            "summary": response_text[:100] + ("..." if len(response_text) > 100 else ""),
            "message_type": message_type,
        },
        pool=pool,
        meta=meta,
    )
    await ws_manager.broadcast(session_id, event.model_dump())
    return event


async def call_agent(agent_id: str, history: list) -> str:
    """Call the appropriate agent API."""
    if agent_id == "sarah":
        return await call_sarah(history)
    return await call_claude(history)


async def load_memory_context(pool: asyncpg.Pool, user_id: str, current_text: str) -> tuple[Optional[str], list]:
    """Load relevant approved memories for the current turn."""
    current_scope = detect_scope(current_text)
    scopes = ["global"]
    if current_scope != "global":
        scopes.append(current_scope)

    memories = await get_memories(pool, user_id=user_id, scopes=scopes, limit=25)
    selected = rank_memories(memories, current_text=current_text, current_scope=current_scope, limit=5)
    memory_context = format_memory_context(selected)

    if selected:
        await mark_memories_used(pool, [memory["memory_id"] for memory in selected])

    return memory_context, selected


async def maybe_persist_memory(
    pool: asyncpg.Pool,
    session_id: str,
    operator_event: EventEnvelope,
    user_id: str,
    message_text: str,
    message_type: str,
) -> Optional[str]:
    """Persist a conservative approved memory from the operator message."""
    candidate = extract_memory_candidate(message_text, message_type)
    if not candidate:
        return None

    memory_id = f"mem_{ULID()}"
    await upsert_memory(
        pool=pool,
        memory_id=memory_id,
        user_id=user_id,
        scope=candidate["scope"],
        category=candidate["category"],
        summary=candidate["summary"],
        detail=candidate["detail"],
        source_session_id=session_id,
        source_event_id=operator_event.event_id,
        source_kind=operator_event.source.kind,
        source_id=operator_event.source.id,
        tags=candidate["tags"],
    )
    return candidate["summary"]


async def run_conference(
    session_id: str,
    thread_id: str,
    raw_messages: list,
    memory_context: Optional[str],
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
):
    """Run the chaired conference protocol."""
    total_steps = 2 + (CONFERENCE_ROUNDS * 2) + 1
    step = 1

    sarah_receipt = await call_agent(
        "sarah",
        build_history_for_agent(
            "sarah",
            raw_messages,
            "Conference mode. Step 1. Give a brief receipt confirmation only. One sentence. No analysis. No extra context.",
            memory_context=memory_context,
        ),
    )
    await persist_and_broadcast(
        "sarah",
        sarah_receipt,
        session_id,
        thread_id,
        pool,
        ws_manager,
        message_type="receipt",
        meta={"mode": "conference", "phase": "receipt", "conference_step": step, "conference_total_steps": total_steps},
    )
    raw_messages.append({"speaker": "sarah", "text": sarah_receipt})
    step += 1

    claude_receipt = await call_agent(
        "claude",
        build_history_for_agent(
            "claude",
            raw_messages,
            "Conference mode. Step 2. Give a brief receipt confirmation only. One sentence. No analysis. No extra context.",
            memory_context=memory_context,
        ),
    )
    await persist_and_broadcast(
        "claude",
        claude_receipt,
        session_id,
        thread_id,
        pool,
        ws_manager,
        message_type="receipt",
        meta={"mode": "conference", "phase": "receipt", "conference_step": step, "conference_total_steps": total_steps},
    )
    raw_messages.append({"speaker": "claude", "text": claude_receipt})
    step += 1

    for round_number in range(1, CONFERENCE_ROUNDS + 1):
        sarah_turn = await call_agent(
            "sarah",
            build_history_for_agent(
                "sarah",
                raw_messages,
                f"Conference mode discussion round {round_number} of {CONFERENCE_ROUNDS}. Speak first in this round. Add new substantive value only. No recap. No conclusion yet. Keep it short.",
                memory_context=memory_context,
            ),
        )
        await persist_and_broadcast(
            "sarah",
            sarah_turn,
            session_id,
            thread_id,
            pool,
            ws_manager,
            message_type="response",
            meta={
                "mode": "conference",
                "phase": "discussion",
                "round": round_number,
                "conference_step": step,
                "conference_total_steps": total_steps,
            },
        )
        raw_messages.append({"speaker": "sarah", "text": sarah_turn})
        step += 1

        claude_turn = await call_agent(
            "claude",
            build_history_for_agent(
                "claude",
                raw_messages,
                f"Conference mode discussion round {round_number} of {CONFERENCE_ROUNDS}. Respond after Sarah. Add new substantive value only. No recap. No conclusion yet. Keep it short.",
                memory_context=memory_context,
            ),
        )
        await persist_and_broadcast(
            "claude",
            claude_turn,
            session_id,
            thread_id,
            pool,
            ws_manager,
            message_type="response",
            meta={
                "mode": "conference",
                "phase": "discussion",
                "round": round_number,
                "conference_step": step,
                "conference_total_steps": total_steps,
            },
        )
        raw_messages.append({"speaker": "claude", "text": claude_turn})
        step += 1

    sarah_brief = await call_agent(
        "sarah",
        build_history_for_agent(
            "sarah",
            raw_messages,
            "Conference mode final brief. Conclude for Matthew. State recommendation, disagreement if any, risks if any, and any approval or decision required. Maximum 4 short lines.",
            memory_context=memory_context,
        ),
    )
    await persist_and_broadcast(
        "sarah",
        sarah_brief,
        session_id,
        thread_id,
        pool,
        ws_manager,
        message_type="summary",
        meta={"mode": "conference", "phase": "brief", "conference_step": step, "conference_total_steps": total_steps},
    )


async def handle_command(
    command: ClientCommand,
    session_id: str,
    pool: asyncpg.Pool,
    ws_manager: ConnectionManager,
):
    """Handle an incoming websocket command."""
    user_message = command.payload.text
    mode = command.payload.mode
    target = command.payload.target or "sarah"
    message_type = command.payload.message_type

    operator_target = None
    if mode == "direct":
        operator_target = Target(kind="agent", id=target, label=target.capitalize())

    operator_event = await persist_event(
        session_id=session_id,
        thread_id=command.thread_id,
        event_type="message.created",
        source=Source(kind="user", id="matthew", label="Matthew"),
        target=operator_target,
        payload={
            "message_id": f"msg_{ULID()}",
            "role": "user",
            "content": [{"type": "text", "text": user_message}],
            "summary": user_message,
            "message_type": message_type,
        },
        pool=pool,
        meta={"message_type": message_type, "mode": mode},
    )
    await ws_manager.broadcast(session_id, operator_event.model_dump())
    await maybe_persist_memory(
        pool=pool,
        session_id=session_id,
        operator_event=operator_event,
        user_id="matthew",
        message_text=user_message,
        message_type=message_type,
    )

    events = await get_events(pool, session_id, command.thread_id, limit=50)
    raw_messages = parse_events_to_raw_messages(events)
    memory_context, _ = await load_memory_context(
        pool,
        user_id="matthew",
        current_text=f"{user_message} {mode} {command.thread_id} {target}",
    )

    if mode == "conference":
        await run_conference(session_id, command.thread_id, raw_messages, memory_context, pool, ws_manager)
        return

    primary_history = build_history_for_agent(target, raw_messages, memory_context=memory_context)
    primary_response = await call_agent(target, primary_history)
    await persist_and_broadcast(
        target,
        primary_response,
        session_id,
        command.thread_id,
        pool,
        ws_manager,
        message_type="response",
        meta={"mode": "direct", "phase": "response"},
    )
