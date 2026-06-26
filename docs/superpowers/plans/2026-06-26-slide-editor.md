# Slide Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real per-slide editor that saves slide content back to session artifacts and makes later PPTX exports use the edited content.

**Architecture:** Add a narrow FastAPI endpoint for one-slide updates, keeping persisted data in `AgentSession.artifacts`. The frontend opens an editor panel for the active slide, calls the endpoint, and refreshes local session state.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy JSON artifacts, React/Vite.

---

### Task 1: Backend Slide Update API

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api.py`
- Test: `backend/tests/test_harness.py`

- [ ] Write a failing test that creates a completed session, updates slide 2, and asserts `outline`, `slides`, and `notes` artifacts all reflect the edit.
- [ ] Run `backend/tests/test_harness.py::test_update_slide_artifacts_keeps_export_sources_in_sync` and confirm it fails because the schema/API helper does not exist.
- [ ] Add `SlideUpdateRequest` with editable fields: `title`, `layout`, `bullets`, `speaker_notes`, `key_message`.
- [ ] Add update logic in `backend/app/api.py` that validates slide number, normalizes bullets, updates related artifacts, commits, and returns `SessionRead`.
- [ ] Run the focused backend test and then the full backend test suite.

### Task 2: Frontend Editor Panel

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles.css`

- [ ] Add `api.updateSlide(sessionId, number, payload)`.
- [ ] Add editor state in `App`, wire the topbar “打开编辑器” button, and pass save handlers into `Preview`.
- [ ] Add `SlideEditor` UI for title, layout, bullets, key message, and speaker notes.
- [ ] After save, replace `session` with the API response, keep the active slide selected, and show a toast.
- [ ] Run `npm run build` in `frontend/`.

### Task 3: Final Verification

**Files:**
- Modify: `todo.md`

- [ ] Mark the Web-side editor TODO as partially completed with the implemented fields.
- [ ] Run `git diff --check`.
- [ ] Run backend tests and frontend build fresh before reporting completion.
