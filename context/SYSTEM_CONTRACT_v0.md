# CERBERUS v0 System Contract
## Drafted by Sarah (GPT 5.4) — 2 April 2026

---

## Scope
This draft defines:

1. **Core message envelope**
2. **Event taxonomy**
3. **Minimal field requirements**
4. **Implementation rules**
5. **Suggested storage mapping**

It is intentionally compact and backend-first.

---

## 1. Design Goals

The contract should support:

- Live WebSocket delivery
- Durable event storage
- Replay of sessions
- Multiple agent types
- Human approvals / governance later
- Compact messages with optional externalized artifacts
- Vendor-agnostic agent/task execution

Principles:

- **Append-only event log**
- **One canonical envelope for all events**
- **Small required field set**
- **Extensible payloads**
- **Stable IDs everywhere**

---

## 2. Core Message Envelope

Every event in CERBERUS uses the same top-level shape.

```json
{
  "event_id": "evt_01HXYZ...",
  "session_id": "ses_01HXYZ...",
  "thread_id": "thr_main",
  "run_id": "run_01HXYZ...",
  "parent_event_id": "evt_01HABC...",
  "event_type": "message.created",
  "source": {
    "kind": "agent",
    "id": "sarah",
    "label": "Sarah"
  },
  "target": {
    "kind": "agent",
    "id": "claude",
    "label": "Claude"
  },
  "timestamp": "2026-04-02T12:00:00Z",
  "sequence": 42,
  "status": "completed",
  "visibility": "thread",
  "payload": {},
  "artifacts": [],
  "meta": {}
}
```

---

## 3. Envelope Field Definitions

### Required Fields

**`event_id`** — Unique event identifier. String, immutable. Recommended: ULID.

**`session_id`** — Groups all events for one CERBERUS session. String, required on every event.

**`thread_id`** — Logical conversation or execution lane. String. Examples: `thr_main`, `thr_tasks`, `thr_audit`.

**`event_type`** — Machine-readable event name. String, must match taxonomy below.

**`source`** — Describes who/what emitted the event.
```json
{
  "kind": "user | system | agent | worker | tool",
  "id": "stable_id",
  "label": "Human-readable name"
}
```
Required: `kind`, `id`.

**`timestamp`** — ISO 8601 UTC string.

**`sequence`** — Monotonically increasing integer within a session. Used for replay ordering. Assigned by backend.

**`status`** — High-level event lifecycle state.
Allowed v0: `pending`, `streaming`, `completed`, `failed`, `cancelled`.

**`payload`** — Object, event-specific body. Must always exist, even if empty.

### Optional But Strongly Recommended

**`run_id`** — Groups events belonging to one execution run / turn / workflow step.

**`parent_event_id`** — Links derived events to originating event. Useful for replies, task results, approvals.

**`target`** — Same shape as `source`, for directed events.

**`visibility`** — Controls where event should appear.
Allowed v0: `thread`, `panel`, `audit`, `system`.

**`artifacts`** — List of referenced large outputs.
```json
[
  {
    "artifact_id": "art_01...",
    "kind": "text | json | file | log | transcript",
    "name": "task-output.json",
    "mime_type": "application/json",
    "uri": "s3://... or internal://artifact/...",
    "size_bytes": 1024
  }
]
```

**`meta`** — Freeform metadata for tracing/debugging (vendor, model, latency_ms, retry_count, policy tags).

---

## 4. Event Taxonomy v0

Use dotted names. Keep them stable.

### A. Session Lifecycle Events

- `session.created` — Session initialized. Payload: `{title, created_by}`
- `session.updated` — Session metadata changed. Payload: `{changes: {...}}`
- `session.closed` — Session ended. Payload: `{reason}`

### B. Thread Lifecycle Events

- `thread.created` — Payload: `{thread_id, name}`
- `thread.updated` — Payload: `{changes: {name}}`

### C. Message Events (Core Conversational)

- `message.created` — Complete message created. Payload: `{message_id, role, content: [{type, text}], summary}`
- `message.delta` — Streaming partial chunk. Payload: `{message_id, delta: {type, text}}`
- `message.completed` — Marks streaming complete. Payload: `{message_id}`
- `message.failed` — Generation failed. Payload: `{message_id, error_code, error_message}`

### D. Task / Job Events (Vendor-Agnostic Work Dispatch)

- `task.created` — Payload: `{task_id, task_type, requested_by, assigned_to, input}`
- `task.queued` — Payload: `{task_id, queue}`
- `task.started` — Payload: `{task_id}`
- `task.progress` — Payload: `{task_id, percent, status_text}`
- `task.completed` — Payload: `{task_id, result_summary, result}`
- `task.failed` — Payload: `{task_id, error_code, error_message, retryable}`
- `task.cancelled` — Payload: `{task_id, reason}`

### E. Agent Presence / State Events

- `agent.registered` — Payload: `{agent_id, agent_type, capabilities}`
- `agent.status` — Payload: `{agent_id, state, detail}` (states: idle, busy, unavailable, error)

### F. Governance / Approval Events

- `approval.requested` — Payload: `{approval_id, subject_type, subject_id, reason}`
- `approval.granted` — Payload: `{approval_id, granted_by}`
- `approval.denied` — Payload: `{approval_id, denied_by, reason}`
- `policy.violation` — Payload: `{policy_code, severity, message}`

### G. System / Transport Events

- `system.notice` — Payload: `{code, message}`
- `system.error` — Payload: `{code, message, retryable}`
- `transport.disconnected` — Payload: `{connection_id, reason}`
- `transport.reconnected` — Payload: `{connection_id}`

---

## 5. Implementation Rules

1. **Append-only** — Do not mutate historical event payloads. If state changes, emit a new event.
2. **Backend assigns ordering** — Backend assigns `event_id`, `sequence`, canonical `timestamp`. Do not trust client ordering.
3. **event_type is the contract** — Frontend and backend should branch on `event_type`, not ad hoc flags.
4. **Payloads must stay small** — If content is large, store as artifact, include summary in payload, reference artifact in `artifacts`.
5. **Message streaming uses three events** — `message.created` (shell) -> `message.delta` (chunks) -> `message.completed` or `message.failed`.
6. **Tasks are separate from messages** — A task result can produce a message, but task lifecycle should not be encoded as message text.
7. **Visibility is advisory, not security** — `visibility` helps rendering, but real access control must be enforced separately later.

---

## 6. Recommended v0 Event Subsets

### Essential (implement first)
- `session.created`
- `message.created`
- `message.delta`
- `message.completed`
- `message.failed`
- `task.created`
- `task.started`
- `task.completed`
- `task.failed`
- `system.error`

### Reserve Now, Implement Soon
- `approval.requested`
- `approval.granted`
- `approval.denied`
- `policy.violation`
- `agent.status`

---

## 7. Suggested Postgres Storage

### `events` table

| Column | Type | Constraint |
|--------|------|------------|
| event_id | text | primary key |
| session_id | text | not null |
| thread_id | text | not null |
| run_id | text | nullable |
| parent_event_id | text | nullable |
| event_type | text | not null |
| source_kind | text | not null |
| source_id | text | not null |
| source_label | text | nullable |
| target_kind | text | nullable |
| target_id | text | nullable |
| target_label | text | nullable |
| timestamp | timestamptz | not null |
| sequence | bigint | not null |
| status | text | not null |
| visibility | text | nullable |
| payload | jsonb | not null default '{}' |
| artifacts | jsonb | not null default '[]' |
| meta | jsonb | not null default '{}' |

### Indexes
- `(session_id, sequence)`
- `(session_id, thread_id, sequence)`
- `(event_type)`
- `(run_id)`
- `(parent_event_id)`

### Constraint
- unique `(session_id, sequence)`

---

## 8. WebSocket Delivery Contract v0

Server -> client: use the same event envelope.

Client -> server: lighter command shape:
```json
{
  "command": "send_message",
  "session_id": "ses_01...",
  "thread_id": "thr_main",
  "payload": {
    "text": "Start the session"
  }
}
```

Once accepted by backend, commands become canonical events in the event log.

---

## 9. Recommended Backend Module Structure

- `models/envelope.py`
- `models/events.py`
- `services/event_store.py`
- `services/event_bus.py`
- `services/session_service.py`
- `ws/connection_manager.py`

Core flow: receive command -> validate -> convert to canonical event -> persist -> broadcast -> trigger downstream orchestration -> persist results -> broadcast results.

---

## 10. Canonical ID Prefixes

Use consistently:
- `evt_` — events
- `ses_` — sessions
- `thr_` — threads
- `run_` — runs
- `msg_` — messages
- `tsk_` — tasks
- `apr_` — approvals
- `art_` — artifacts

---

## 11. Known v0 Simplifications

Not yet fully defined (next contract layer):
- Session model details
- Thread permissions
- Agent capability registry schema
- Approval state machine
- Artifact storage backend
- Idempotency keys
- Retry semantics
- Deduplication rules
