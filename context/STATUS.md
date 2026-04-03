# Project Status — CERBERUS

*Last updated: 2026-04-03*

## What CERBERUS is

A real-time triadic coordination system. Matthew (operator), Sarah (GPT 5.4), and Claude (Opus 4.6) communicate through a governed interface. Built on FastAPI + WebSocket + PostgreSQL, hosted on Railway, auto-deploys from GitHub.

## Current state

- Core messaging works: operator can send to Sarah, Claude, or both.
- In "both" mode, Sarah replies first; Claude sees Sarah's response before replying.
- Agents see each other's messages with speaker labels (`[Sarah]:`, `[Claude]:`, `[Matthew]:`).
- Context files are loaded as system prompts automatically.
- Prometheus-themed UI is live (3-panel layout, governance controls, event log).
- Session-end reminder modal added to prompt STATUS.md updates.

## Active priorities

- Stabilise the sequential Forge pipeline (Phase 1 bugs under resolution).
- CERBERUS is the coordination layer — keep it functional and lean.
- PKE agent architecture is designed; implementation deferred until pipeline is stable.

## Known issues

- Some governance UI elements (Broadcast mode, Gated mode, Challenge Budget) are visual-only — not wired to the backend yet.
- Agent responses can be verbose. Baseline prompts have been tightened to address this.
- No persistent agent memory between API calls — each message is stateless with full context re-injected.

## Recent decisions

- System prompts restructured: per-agent baseline identity file + shared STATUS.md (this file).
- Old multi-file doctrine/contract/summary approach replaced with leaner two-file structure.
- Agents instructed not to restate their operating posture — behaviour should demonstrate it.

## Prometheus Forge — current state

Forge is the core product: an AI-powered courseware generation platform that compresses training material production from weeks to minutes. Repo: `PrometheusDevCreator/Prometheus-Forge` (private). Stack: React/Vite frontend, FastAPI/Python backend, Claude Sonnet (generation) + Claude Haiku (suggestions).

**Pipeline:** Course Manager → Define → Research → Design → Schedule → Assess → Generate. Each stage builds on the previous. Outputs include PPTX slide decks, SCORM packages, facilitator guides, participant workbooks, assessment banks, and session plans.

**What works:** End-to-end pipeline generates real courseware. Bulk upload for Research is operational. Multiple template packs supported (Prometheus Dark, Prometheus Light, Rabdan White-and-Blue).

**Phase 1 bugs (active):** Generate stage timing out or producing partial output on large courses. Research-to-Design data handoff occasionally drops learning outcomes. Schedule component has a React state warning. Template switch to Rabdan pack not yet verified clean. `content_placer.py` (839 lines) identified as dead code. Template extraction pipeline not yet built (schemas exist, pipeline does not).

**PKE agent architecture:** Fully designed, not yet implemented. Nine named agents (Themic Orchestrator, Delphic Interpreter, Athenic Researcher, Daedalic Architect, Hephestian Builder, Alethean Verifier, Eris Challenger, Solonic Arbitrator, Aegis Protector) plus Hermetic infrastructure layer. Implementation sequence: stabilise current pipeline → self-review loop → research agent → full agentic loop. Blocked on pipeline stability.

**Target market:** Defence, security, resilience, strategic governance organisations. Primary client relationship: Rabdan Academy, Abu Dhabi.

## Open questions

- How to handle STATUS.md updates — manual for now, could be semi-automated later.
- Whether to add a `/status` slash command in the UI for quick updates.
