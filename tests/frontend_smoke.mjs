import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const htmlPath = path.join(__dirname, "..", "static", "index.html");
const html = await fs.readFile(htmlPath, "utf8");

const fetchCalls = [];
const sentMessages = [];
const sockets = [];

class FakeWebSocket {
  constructor(url) {
    this.url = url;
    sockets.push(this);
    queueMicrotask(() => this.onopen && this.onopen());
  }

  send(data) {
    sentMessages.push(JSON.parse(data));
  }

  close() {
    this.onclose && this.onclose();
  }

  emit(event) {
    this.onmessage && this.onmessage({ data: JSON.stringify(event) });
  }
}

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable",
  url: "http://localhost:8000/",
  pretendToBeVisual: true,
  beforeParse(window) {
    window.fetch = async (url, options = {}) => {
      fetchCalls.push({ url, options });

      if (url === "/api/sessions") {
        return {
          async json() {
            return { session_id: "ses_test_123456", user_id: "matthew" };
          },
        };
      }

      return {
        async json() {
          return { events: [] };
        },
      };
    };

    window.WebSocket = FakeWebSocket;
    window.console = console;
  },
});

await new Promise((resolve) => setTimeout(resolve, 50));

const { document } = dom.window;
const sendBtn = document.getElementById("sendBtn");
const messageInput = document.getElementById("messageInput");
const approvalToggle = document.getElementById("toggleApproval");

assert.equal(approvalToggle.classList.contains("on"), true, "approval should default to on");

document.querySelector('.mode-btn[data-mode="direct"]').click();
await new Promise((resolve) => setTimeout(resolve, 10));
assert.equal(
  fetchCalls.at(-1).url.includes("thread_id=thr_direct_sarah"),
  true,
  "direct mode should load Sarah's private thread"
);

messageInput.value = "Private test";
sendBtn.click();

assert.equal(sentMessages.length, 1, "one websocket command should be sent");
assert.equal(sentMessages[0].thread_id, "thr_direct_sarah");
assert.equal(sentMessages[0].payload.target, "sarah");
assert.equal(sentMessages[0].payload.approval_required, true);
assert.equal(sendBtn.disabled, true, "send button should disable while waiting");

sockets[0].emit({
  event_id: "evt_operator",
  thread_id: "thr_direct_sarah",
  event_type: "message.created",
  source: { kind: "user", id: "matthew", label: "Matthew" },
  timestamp: "2026-04-03T10:00:00Z",
  payload: { content: [{ type: "text", text: "Private test" }] },
});

assert.equal(sendBtn.disabled, true, "operator echo should not re-enable sending");

sockets[0].emit({
  event_id: "evt_sarah",
  thread_id: "thr_direct_sarah",
  event_type: "message.created",
  source: { kind: "agent", id: "sarah", label: "Sarah" },
  target: { kind: "user", id: "matthew", label: "Matthew" },
  timestamp: "2026-04-03T10:00:01Z",
  payload: { content: [{ type: "text", text: "Approved only after review" }], message_type: "response" },
});

assert.equal(sendBtn.disabled, false, "agent response should release the send button");
assert.equal(
  document.getElementById("messageThread").textContent.includes("Pending operator approval"),
  true,
  "agent responses should be gated behind approval when approval is enabled"
);

document.getElementById("muteSarah").click();
messageInput.value = "Muted test";
sendBtn.click();
sockets[0].emit({
  event_id: "evt_sarah_muted",
  thread_id: "thr_direct_sarah",
  event_type: "message.created",
  source: { kind: "agent", id: "sarah", label: "Sarah" },
  timestamp: "2026-04-03T10:00:02Z",
  payload: { content: [{ type: "text", text: "Muted response" }] },
});

assert.equal(sendBtn.disabled, false, "muted responses should still clear pending state");

document.getElementById("muteSarah").click();
document.querySelector('.mode-btn[data-mode="conference"]').click();
await new Promise((resolve) => setTimeout(resolve, 10));
messageInput.value = "Conference test";
sendBtn.click();

assert.equal(sentMessages.at(-1).thread_id, "thr_main");
assert.equal(sendBtn.disabled, true, "conference should hold send until the final brief");

sockets[0].emit({
  event_id: "evt_conf_sarah_receipt",
  thread_id: "thr_main",
  event_type: "message.created",
  source: { kind: "agent", id: "sarah", label: "Sarah" },
  timestamp: "2026-04-03T10:01:00Z",
  payload: { content: [{ type: "text", text: "Receipt." }], message_type: "receipt" },
  meta: { mode: "conference", phase: "receipt", conference_step: 1, conference_total_steps: 9 },
});
sockets[0].emit({
  event_id: "evt_conf_claude_receipt",
  thread_id: "thr_main",
  event_type: "message.created",
  source: { kind: "agent", id: "claude", label: "Claude" },
  timestamp: "2026-04-03T10:01:01Z",
  payload: { content: [{ type: "text", text: "Receipt." }], message_type: "receipt" },
  meta: { mode: "conference", phase: "receipt", conference_step: 2, conference_total_steps: 9 },
});
assert.equal(sendBtn.disabled, true, "conference receipts should not unlock input");

sockets[0].emit({
  event_id: "evt_conf_final",
  thread_id: "thr_main",
  event_type: "message.created",
  source: { kind: "agent", id: "sarah", label: "Sarah" },
  timestamp: "2026-04-03T10:01:09Z",
  payload: { content: [{ type: "text", text: "Final brief." }], message_type: "summary" },
  meta: { mode: "conference", phase: "brief", conference_step: 9, conference_total_steps: 9 },
});
assert.equal(sendBtn.disabled, false, "conference should unlock only after Sarah's final brief");

document.getElementById("sessionEndConfirm").click();
await new Promise((resolve) => setTimeout(resolve, 20));
assert.equal(sockets.length, 1, "terminate should not trigger websocket reconnect");

console.log("frontend-smoke-ok");
