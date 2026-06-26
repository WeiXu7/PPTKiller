# AGENTS.md

This file gives future agents durable project context for PPTKiller. Follow it before making changes in this repository.

## Project purpose

PPTKiller is a professional PPT Agent MVP. It generates or modifies presentations from a user topic, uploaded materials, citations, and images. The product must preserve a transparent Agent workflow: users can see research, citations, image sources, approval gates, generated slides, speaker notes, and final PPTX exports.

The repository is already connected to:

```text
git@github.com:WeiXu7/PPTKiller.git
```

## Current architecture

- Frontend: React + Vite in `frontend/`.
- Backend: FastAPI + Pydantic + SQLAlchemy + SQLite in `backend/`.
- Agent workflow: Harness-style steps in `backend/app/services/harness.py`.
- Model provider: DeepSeek OpenAI-compatible API, default model `deepseek-v4-flash`.
- Research/image providers: Tavily, Crossref, Unsplash, with provider status in `backend/app/services/providers.py`.
- PPT export: Artifact Tool runtime in `scripts/ppt-runtime/generate-deck.mjs`, invoked from `backend/app/services/pptx_export.py`.
- Design references: `docs/design/`.
- Outstanding work: `todo.md`.

## Local run targets

Preferred local ports in this workspace:

```bash
env CORS_ORIGINS=http://127.0.0.1:5180 .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

```bash
cd frontend
env VITE_API_URL=http://127.0.0.1:8010/api/v1 npm run dev
```

The frontend is commonly opened at:

```text
http://127.0.0.1:5180/
```

## Privacy and Git rules

Do not commit private runtime state or generated artifacts.

Never commit:

- `.env` or `**/.env`, especially `backend/app/.env`.
- API keys, tokens, SSH keys, or provider credentials.
- `.venv/`.
- `frontend/node_modules/`, `**/node_modules/`.
- `frontend/.npm-cache/`.
- `frontend/.npmrc`.
- `frontend/dist/`.
- `backend/data/`, including SQLite databases and uploaded user files.
- `backend/generated/`, including PPTX files, thumbnails, montage images, QA layouts, downloaded images.

Before committing, run at least:

```bash
git status --short --branch
git diff --cached --name-only
```

If adding a broad set of files, also check ignored private files with:

```bash
git check-ignore -v backend/app/.env backend/data/pptkiller.db frontend/node_modules/vite/package.json frontend/dist/index.html .venv/pyvenv.cfg
```

If doing a secret scan, scan only tracked/staged/project files, not the user's real `.env` contents.

## Development conventions

- Preserve the front/back separation.
- Keep API responses grounded in real backend state; do not reintroduce fake research counts, fake citations, or fake verification states.
- Keep human approval gates explicit before final PPTX export.
- Prefer small, testable increments.
- Use `rg` for searching files.
- Use `apply_patch` for source edits.
- Avoid destructive Git commands unless the user explicitly requests them.
- Treat existing uncommitted changes as user-owned unless you made them in the current task.

## Backend notes

- Main router: `backend/app/api.py`.
- Schemas: `backend/app/schemas.py`.
- DB models: `backend/app/models.py`.
- Settings: `backend/app/config.py`.
- Harness steps: `backend/app/services/harness.py`.
- Agent service implementations: `backend/app/services/agent_services.py`.
- File parsers: `backend/app/services/parsers.py`.
- Provider integrations: `backend/app/services/providers.py`.
- PPTX export and thumbnail/manifest helpers: `backend/app/services/pptx_export.py`.

Run backend tests with:

```bash
.venv/bin/python -m pytest backend/tests -q
```

## Frontend notes

- Main app: `frontend/src/App.jsx`.
- API client: `frontend/src/api.js`.
- Styles: `frontend/src/styles.css`.
- Frontend-specific instructions also exist in `frontend/AGENTS.md`; follow them for work under `frontend/`.

Run frontend build with:

```bash
cd frontend
npm run build
```

## Design direction

Use the existing selected visual direction:

- White/neutral professional workspace.
- Navy primary actions.
- Violet Agent/progress accents.
- Green completion states.
- Orange approval/warning semantics.
- Three-pane authenticated Agent execution workspace.

Design reference and QA assets live in:

```text
docs/design/
```

When making substantial UI changes, compare against the existing design assets and preserve the product's professional PPT-Agent feel.

## PPT export expectations

The export engine should continue to:

- Generate editable PPTX.
- Render per-slide PNG thumbnails.
- Generate layout JSON and montage QA output.
- Preserve citations and image attribution where available.
- Include speaker notes when enabled.
- Fail visibly rather than silently returning invalid PPTX.

Frontend completed sessions should show real rendered PPT thumbnails via the authenticated export manifest APIs.

## Key unfinished work

See `todo.md`. The highest-value next items are:

1. Web-side per-slide editor.
2. Image replacement and per-slide image assignment.
3. Chart/data-native slide types from Excel/CSV.
4. Export QA panel with warnings.
5. OCR/vision parsing for scanned PDFs and image-only files.

