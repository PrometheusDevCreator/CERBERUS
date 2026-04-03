import os
import sys
import unittest
from pathlib import Path
from contextlib import asynccontextmanager
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import get_memory_entries, get_session_events
from app.models import ClientCommand, CommandPayload
from app.orchestrator import handle_command, parse_events_to_raw_messages


class FakeConnection:
    def __init__(self):
        self.events = []
        self.memories = []

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def execute(self, query, *args):
        if "CREATE TABLE" in query or "CREATE INDEX" in query or "pg_advisory_xact_lock" in query:
            return

        if "INSERT INTO events" in query:
            self.events.append(
                {
                    "event_id": args[0],
                    "session_id": args[1],
                    "thread_id": args[2],
                    "run_id": args[3],
                    "parent_event_id": args[4],
                    "event_type": args[5],
                    "source_kind": args[6],
                    "source_id": args[7],
                    "source_label": args[8],
                    "target_kind": args[9],
                    "target_id": args[10],
                    "target_label": args[11],
                    "timestamp": args[12],
                    "sequence": args[13],
                    "status": args[14],
                    "visibility": args[15],
                    "payload": args[16],
                    "artifacts": args[17],
                    "meta": args[18],
                }
            )
            return

        if "INSERT INTO memories" in query:
            self.memories.append(
                {
                    "memory_id": args[0],
                    "user_id": args[1],
                    "scope": args[2],
                    "category": args[3],
                    "summary": args[4],
                    "detail": args[5],
                    "source_session_id": args[6],
                    "source_event_id": args[7],
                    "source_kind": args[8],
                    "source_id": args[9],
                    "tags": args[10],
                    "status": "active",
                    "created_at": "2026-04-03T00:00:00+00:00",
                    "updated_at": "2026-04-03T00:00:00+00:00",
                    "last_used_at": None,
                }
            )
            return

        if "UPDATE memories" in query and "WHERE memory_id = $1" in query:
            memory_id = args[0]
            for memory in self.memories:
                if memory["memory_id"] == memory_id:
                    memory["category"] = args[1]
                    memory["detail"] = args[2]
                    memory["source_session_id"] = args[3]
                    memory["source_event_id"] = args[4]
                    memory["source_kind"] = args[5]
                    memory["source_id"] = args[6]
                    memory["tags"] = args[7]
                    memory["updated_at"] = "2026-04-03T00:00:01+00:00"
                    return

        if "UPDATE memories" in query and "last_used_at = NOW()" in query:
            memory_ids = set(args[0])
            for memory in self.memories:
                if memory["memory_id"] in memory_ids:
                    memory["last_used_at"] = "2026-04-03T00:00:02+00:00"

    async def fetchval(self, query, *args):
        if "MAX(sequence)" in query:
            session_id = args[0]
            sequences = [event["sequence"] for event in self.events if event["session_id"] == session_id]
            return (max(sequences) + 1) if sequences else 0

        if "SELECT memory_id" in query:
            user_id, scope, summary = args
            summary = summary.lower()
            for memory in self.memories:
                if (
                    memory["user_id"] == user_id
                    and memory["scope"] == scope
                    and memory["status"] == "active"
                    and memory["summary"].lower() == summary
                ):
                    return memory["memory_id"]
        return None

    async def fetch(self, query, *args):
        if "FROM events" in query:
            session_id = args[0]
            if len(args) == 3:
                thread_id = args[1]
                limit = args[2]
                rows = [event for event in self.events if event["session_id"] == session_id and event["thread_id"] == thread_id]
            else:
                limit = args[1]
                rows = [event for event in self.events if event["session_id"] == session_id]

            rows = sorted(rows, key=lambda event: event["sequence"], reverse=True)[:limit]
            return list(reversed(rows))

        if "FROM memories" in query:
            user_id = args[0]
            if len(args) == 3:
                scopes = set(args[1])
                limit = args[2]
                rows = [
                    memory for memory in self.memories
                    if memory["user_id"] == user_id and memory["status"] == "active" and memory["scope"] in scopes
                ]
            else:
                limit = args[1]
                rows = [memory for memory in self.memories if memory["user_id"] == user_id and memory["status"] == "active"]

            rows = sorted(rows, key=lambda memory: memory["updated_at"], reverse=True)[:limit]
            return rows

        return []


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self):
        self.conn = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeWSManager:
    def __init__(self):
        self.events = []

    async def broadcast(self, session_id, event):
        self.events.append((session_id, event))


class BackendSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_events_handles_string_payloads(self):
        events = [
            {
                "event_type": "message.created",
                "source_id": "matthew",
                "payload": '{"content":[{"type":"text","text":"Hello"}]}',
            }
        ]
        parsed = parse_events_to_raw_messages(events)
        self.assertEqual(parsed, [{"speaker": "matthew", "text": "Hello"}])

    async def test_conference_flow_runs_full_chair_protocol(self):
        pool = FakePool()
        ws_manager = FakeWSManager()
        command = ClientCommand(
            command="send_message",
            session_id="ses_test",
            thread_id="thr_main",
            payload=CommandPayload(text="Test conference", mode="conference", message_type="query"),
        )

        sarah_responses = [
            "Sarah receipt",
            "Sarah round 1",
            "Sarah round 2",
            "Sarah round 3",
            "Sarah final brief",
        ]
        claude_responses = [
            "Claude receipt",
            "Claude round 1",
            "Claude round 2",
            "Claude round 3",
        ]

        with patch("app.orchestrator.call_sarah", side_effect=sarah_responses), patch(
            "app.orchestrator.call_claude", side_effect=claude_responses
        ):
            await handle_command(command, "ses_test", pool, ws_manager)

        self.assertEqual(len(ws_manager.events), 10)
        ordered_sources = [event["source"]["id"] for _, event in ws_manager.events]
        self.assertEqual(
            ordered_sources,
            ["matthew", "sarah", "claude", "sarah", "claude", "sarah", "claude", "sarah", "claude", "sarah"],
        )
        self.assertEqual(ws_manager.events[1][1]["payload"]["message_type"], "receipt")
        self.assertEqual(ws_manager.events[-1][1]["payload"]["message_type"], "summary")
        self.assertEqual(ws_manager.events[-1][1]["meta"]["phase"], "brief")

    async def test_direct_threads_stay_isolated(self):
        pool = FakePool()
        ws_manager = FakeWSManager()

        sarah_command = ClientCommand(
            command="send_message",
            session_id="ses_test",
            thread_id="thr_direct_sarah",
            payload=CommandPayload(text="Sarah private", mode="direct", target="sarah", message_type="query"),
        )
        claude_command = ClientCommand(
            command="send_message",
            session_id="ses_test",
            thread_id="thr_direct_claude",
            payload=CommandPayload(text="Claude private", mode="direct", target="claude", message_type="query"),
        )

        with patch("app.orchestrator.call_sarah", return_value="Sarah private reply"), patch(
            "app.orchestrator.call_claude", return_value="Claude private reply"
        ):
            await handle_command(sarah_command, "ses_test", pool, ws_manager)
            await handle_command(claude_command, "ses_test", pool, ws_manager)

        sarah_threads = {event["thread_id"] for _, event in ws_manager.events if event["source"]["id"] == "sarah"}
        claude_threads = {event["thread_id"] for _, event in ws_manager.events if event["source"]["id"] == "claude"}

        self.assertEqual(sarah_threads, {"thr_direct_sarah"})
        self.assertEqual(claude_threads, {"thr_direct_claude"})

    async def test_session_events_are_canonicalized_for_frontend(self):
        fake_rows = [
            {
                "event_id": "evt_1",
                "session_id": "ses_test",
                "thread_id": "thr_main",
                "run_id": None,
                "parent_event_id": None,
                "event_type": "message.created",
                "source_kind": "user",
                "source_id": "matthew",
                "source_label": "Matthew",
                "target_kind": "agent",
                "target_id": "sarah",
                "target_label": "Sarah",
                "timestamp": "2026-04-03T00:00:00+00:00",
                "sequence": 0,
                "status": "completed",
                "visibility": "thread",
                "payload": '{"content":[{"type":"text","text":"Hello"}]}',
                "artifacts": "[]",
                "meta": '{"message_type":"query"}',
            }
        ]

        with patch("app.main.get_events", return_value=fake_rows):
            result = await get_session_events("ses_test", "thr_main", 100)

        event = result["events"][0]
        self.assertEqual(event["source"]["id"], "matthew")
        self.assertEqual(event["target"]["id"], "sarah")
        self.assertEqual(event["payload"]["content"][0]["text"], "Hello")

    async def test_operator_memory_persists_and_is_injected_across_sessions(self):
        pool = FakePool()
        ws_manager = FakeWSManager()

        remember_command = ClientCommand(
            command="send_message",
            session_id="ses_memory_a",
            thread_id="thr_direct_sarah",
            payload=CommandPayload(
                text="Remember: default to conference mode when both agents are needed.",
                mode="direct",
                target="sarah",
                message_type="instruction",
            ),
        )

        with patch("app.orchestrator.call_sarah", return_value="Stored"):
            await handle_command(remember_command, "ses_memory_a", pool, ws_manager)

        self.assertEqual(len(pool.conn.memories), 1)
        self.assertEqual(pool.conn.memories[0]["scope"], "cerberus")

        captured_histories = []

        async def fake_sarah(history):
            captured_histories.append(history)
            return "Using memory"

        recall_command = ClientCommand(
            command="send_message",
            session_id="ses_memory_b",
            thread_id="thr_direct_sarah",
            payload=CommandPayload(
                text="How should I route a task that needs both agents?",
                mode="direct",
                target="sarah",
                message_type="query",
            ),
        )

        with patch("app.orchestrator.call_sarah", side_effect=fake_sarah):
            await handle_command(recall_command, "ses_memory_b", pool, ws_manager)

        rendered_history = "\n".join(item["content"] for item in captured_histories[0])
        self.assertIn("[Persistent Memory]", rendered_history)
        self.assertIn("default to conference mode when both agents are needed", rendered_history)

    async def test_non_durable_query_does_not_create_memory(self):
        pool = FakePool()
        ws_manager = FakeWSManager()
        command = ClientCommand(
            command="send_message",
            session_id="ses_test",
            thread_id="thr_direct_sarah",
            payload=CommandPayload(text="What is the current status?", mode="direct", target="sarah", message_type="query"),
        )

        with patch("app.orchestrator.call_sarah", return_value="Status reply"):
            await handle_command(command, "ses_test", pool, ws_manager)

        self.assertEqual(pool.conn.memories, [])

    async def test_memory_endpoint_returns_active_entries(self):
        pool = FakePool()
        pool.conn.memories.append(
            {
                "memory_id": "mem_1",
                "user_id": "matthew",
                "scope": "global",
                "category": "preference",
                "summary": "Prefer concise replies.",
                "detail": "Prefer concise replies.",
                "source_session_id": "ses_a",
                "source_event_id": "evt_a",
                "source_kind": "user",
                "source_id": "matthew",
                "tags": "[]",
                "status": "active",
                "created_at": "2026-04-03T00:00:00+00:00",
                "updated_at": "2026-04-03T00:00:00+00:00",
                "last_used_at": None,
            }
        )

        from app import main as main_module

        original_pool = main_module.db_pool
        main_module.db_pool = pool
        try:
            result = await get_memory_entries(user_id="matthew", scope=None, limit=10)
        finally:
            main_module.db_pool = original_pool

        self.assertEqual(len(result["memories"]), 1)
        self.assertEqual(result["memories"][0]["summary"], "Prefer concise replies.")


if __name__ == "__main__":
    unittest.main()
