# Architecture Visuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add editable architecture-diagram slides for technical and framework-heavy PPT topics.

**Architecture:** The outline service marks suitable slides with `layout: "architecture"` and diagram metadata. The export layer passes that metadata through unchanged, and both Node and Python fallback renderers draw native diagram shapes.

**Tech Stack:** FastAPI service code, Python tests, Artifact Tool Node runtime, python-pptx fallback, React layout selector.

---

### Task 1: Outline And QA Rules

**Files:**
- Modify: `backend/tests/test_harness.py`
- Modify: `backend/app/services/agent_services.py`
- Modify: `backend/app/services/pptx_export.py`

- [ ] Write failing tests for architecture fallback outline and image-warning behavior.
- [ ] Run `backend/tests/test_harness.py::test_fallback_outline_adds_architecture_for_technical_framework`.
- [ ] Add architecture slide detection and default diagram metadata.
- [ ] Exclude `architecture` from image-required warning logic.
- [ ] Re-run the focused tests.

### Task 2: Export Rendering

**Files:**
- Modify: `scripts/ppt-runtime/generate-deck.mjs`
- Modify: `backend/app/services/pptx_export.py`

- [ ] Add `buildArchitectureSlide` to the Node runtime.
- [ ] Route `layout === "architecture"` to that renderer.
- [ ] Add architecture rendering to Python fallback PPT and QA PNG.
- [ ] Run `node --check scripts/ppt-runtime/generate-deck.mjs`.

### Task 3: API And Frontend Layout Support

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `frontend/src/App.jsx`

- [ ] Add `architecture` to slide update layout validation.
- [ ] Add `architecture` to the frontend layout selector.
- [ ] Run backend tests and frontend build.
