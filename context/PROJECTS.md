# Active Projects

## 1. Prometheus Forge

**What:** AI-powered courseware generation platform. Produces PPTX, SCORM, facilitator guides, workbooks, assessments, and session plans from structured course definitions.
**Stack:** React/Vite frontend, FastAPI/Python backend, Claude Sonnet + Haiku. Repo: `PrometheusDevCreator/Prometheus-Forge` (private).
**Milestone:** Phase 1 stability — get the sequential pipeline reliably generating complete courseware for production-sized courses.
**State:** Pipeline works end-to-end but has stability issues on large courses.
**Top 3 issues:** (1) Generate stage times out or produces partial output on large courses. (2) Research-to-Design handoff occasionally drops learning outcomes. (3) Rabdan template pack switch not verified clean.
**Next steps:** Instrument Generate to classify failure mode. Fix the critical path. Verify Rabdan template pack.

## 2. CERBERUS

**What:** Real-time triadic coordination interface — Matthew, Sarah, Claude communicating through a governed environment.
**Stack:** FastAPI + WebSocket + PostgreSQL, hosted on Railway. Repo: `PrometheusDevCreator/CERBERUS`.
**Milestone:** Functional coordination tool with Conference and Direct modes.
**State:** Core messaging works. Conference and Direct modes operational. Agents load context automatically.
**Top 3 issues:** (1) Agents sometimes default to Forge work instead of addressing the actual conversation. (2) No persistent memory between sessions. (3) Governance UI controls are visual placeholders only.
**Next steps:** Test new baseline personalities. Evaluate persistent memory approaches.
