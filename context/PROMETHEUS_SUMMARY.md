# Prometheus Forge — Platform Summary

**Prometheus Education Systems (PES)**
**Date:** April 2026

---

## What Is Prometheus Forge?

Prometheus Forge is an AI-powered courseware generation platform built by Prometheus Education Systems. It compresses the production of professional training materials — a process that traditionally takes subject matter experts and instructional designers weeks or months — into minutes.

The platform is designed for organisations operating in defence, security, resilience, strategic governance, and crisis response. Its primary client relationship is with Rabdan Academy in Abu Dhabi.

Prometheus Forge does not simply generate slide decks. It produces a full suite of coordinated training outputs from a single course definition:

- **Presentations (PPTX)** — branded, structured slide decks with facilitator-ready content
- **SCORM packages** — standards-compliant e-learning modules for deployment to any LMS
- **Facilitator Guides** — detailed session-by-session guides for instructors delivering the material
- **Lesson Plans** — structured plans aligned to learning outcomes at the lesson level
- **Timetables** — scheduled delivery plans with session sequencing and time allocations
- **Course Specification Sheets** — formal course documentation covering objectives, structure, and assessment strategy

All outputs are generated from a single course definition, ensuring consistency across every deliverable.

---

## How It Works

The platform follows a structured pipeline that mirrors the way experienced instructional designers build courses, but automates each stage with AI:

1. **Course Manager** — The user's workspace. Courses are created, managed, and tracked from here.
2. **Define** — The user establishes the course identity: title, description, target audience, duration, and high-level aims.
3. **Research** — Course Learning Outcomes (CLOs), lessons, and topics are defined. Content can be entered manually or uploaded in bulk via CSV/XLSX. The system supports append-based uploads with sanity checks for duplicates, empty rows, and formatting issues.
4. **Design** — The AI generates detailed content for each topic within the course hierarchy, aligned to the defined learning outcomes and Bloom's taxonomy levels.
5. **Schedule** — Lessons are sequenced into a timetable. Anchor lessons (Capstone, MCQ assessments, Final Assessment) are placed first, with remaining sessions distributed around them.
6. **Assess** — Assessment strategies are generated, tied to the content produced in earlier stages so that assessment questions are drawn from actual course material rather than generic templates.
7. **Generate** — The user triggers output generation. The platform produces the full suite of deliverables, branded to the selected template pack.

---

## Current Build State

Prometheus Forge is a working platform. The core pipeline — from course definition through to multi-format export — is functional. The technology stack:

- **Frontend:** React/Vite with Zustand state management, styled to the Prometheus brand palette (burnt orange, gold, dark backgrounds)
- **Backend:** FastAPI (Python)
- **AI Models:** Claude Sonnet for content generation; Claude Haiku for inline suggestions and lighter tasks
- **Template System:** Branded PPTX template packs (Prometheus Dark, Prometheus White and Blue / Rabdan styling)
- **Deployment Options:** Cloud-native, with architecture supporting secure local and air-gapped configurations for sensitive environments

**What works:**
The end-to-end pipeline generates real courseware. Courses can be defined, researched, designed, scheduled, assessed, and exported. Bulk upload for Research content is operational. Multiple template packs are supported.

**Known issues under active resolution:**
- The scheduler occasionally displaces anchor lessons (Capstone, assessments) by inserting filler blocks too early in the sequence
- Export mapping errors where lessons are repeated or missing in PPTX output
- Upload counter display not updating correctly in the Research section
- A minor React state warning in the Schedule component
- Template switch to the White and Blue (Rabdan) pack was tasked but not yet verified clean

These are Phase 1 bug fixes in the current execution plan. Once resolved, a full end-to-end verification pass will confirm the pipeline is clean.

---

## What Is the PKE?

The **Prometheus Knowledge Engine (PKE)** is the AI intelligence layer inside Prometheus Forge. Today, the PKE is the system of prompts, logic, and generation sequences that drives every AI-powered action in the platform — from generating learning outcomes to producing assessment questions to building slide content.

In its current form, the PKE operates as a structured sequential pipeline: each stage of the course-building process calls AI with carefully engineered prompts built on SMEAC principles (Situation, Mission, Execution, Any Questions, Check Understanding — drawn from military operational planning methodology). The outputs of each stage carry forward as context for the next, ensuring coherence across the full course.

### What the PKE Is Becoming

The PKE is being evolved from a sequential prompt pipeline into a **multi-agent architecture** — a team of specialised AI agents, each with a defined role, authority boundary, and area of expertise. The architecture is fully designed and named:

| Agent | Role |
|---|---|
| **Themic Orchestrator** | Central coordinator. Routes tasks, manages pipeline flow, resolves sequencing. |
| **Delphic Interpreter** | Interprets user intent. Translates natural language inputs into structured parameters the system can act on. |
| **Athenic Researcher** | Conducts deep research. Supported by five specialist sub-agents (the Muses) covering different knowledge domains. |
| **Daedalic Architect** | Holds pedagogical authority. Owns instructional design decisions — Bloom's taxonomy alignment, learning pathway structure, curriculum architecture. |
| **Hephaestionic Constructor** | Builds the outputs. Responsible for assembling content into deliverable formats (slides, documents, SCORM). |
| **Alethean Verifier** | Quality assurance for objective, verifiable facts. Checks accuracy, consistency, and factual correctness. |
| **Eris Challenger** | Quality assurance for judgment calls. Challenges assumptions, flags weak reasoning, stress-tests design decisions. |
| **Solonic Arbitrator** | Conflict resolution. Activates when agents disagree (reactive mode) and provides advisory checks at pipeline transitions. |
| **Aegis Protector** | Security and compliance. Ensures outputs meet policy, regulatory, and organisational standards. |

Two additional architectural layers support these agents:

- **The Hermetic Layer** — Infrastructure services: logging, telemetry, configuration, and inter-agent communication
- **The Forge** — The user-facing entry point; the interface through which all generation is initiated

A sharp boundary rule governs the QA agents: Alethean handles anything objectively verifiable; Eris handles anything requiring judgment. This prevents overlap and ensures clear accountability.

### Why This Matters

The current sequential pipeline works, but it processes each stage in isolation with only carry-forward summaries connecting them. The agent architecture allows for genuine cross-referencing, self-review, challenge, and arbitration — the same dynamics that make a strong human instructional design team effective.

The implementation plan is deliberate: the current pipeline must be fully stable and verified before agent architecture begins. The sequence is:

1. Stabilise the current sequential pipeline (in progress)
2. Introduce a self-review loop on existing generation
3. Deploy the Research agent as the first standalone agent
4. Build toward the full agentic loop

This is not speculative. The architecture is defined, the agent boundaries are set, and the naming convention is locked. What remains is execution — in the right order.

---

## Deployment and Market Position

Prometheus Forge is positioned for enterprise-scale deployment in organisations where:

- Training material production is a recurring, high-volume requirement
- Content must meet formal standards (accreditation bodies, regulatory compliance, institutional quality frameworks)
- Security constraints may require local or air-gapped deployment rather than cloud-only solutions
- Speed matters — operational tempo demands rapid course development without sacrificing quality

The platform is not a slide generator with AI bolted on. It is a courseware production system that understands curriculum structure, learning outcome alignment, assessment design, and branded output formatting as an integrated whole.

---

*Prometheus Education Systems — Abu Dhabi, UAE*
