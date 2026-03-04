# CLAUDE.md

Repository-specific guidance for Claude (and other coding assistants).

## Project Scope

Orchestrator is a web app that manages coding tasks through staged agent workflows:
- planning
- plan review
- implementation
- code review
- PR creation

Main stack:
- Backend: FastAPI + SQLAlchemy + Alembic (`backend/`)
- Frontend: Next.js App Router (`frontend/`)
- Runtime: Docker Compose (`docker-compose.yml`)

## Preferred Commands

Use the root `Makefile` whenever possible:

- `make up` / `make down` / `make ps`
- `make backend-check` (ruff + pytest)
- `make frontend-check` (lint + build)
- `make check` (full local checks)
- `make backend-migrate-head`

Default Docker host ports:
- Frontend: `13000`
- Backend: `18000`

Override when needed:
- `ORCHESTRATOR_FRONTEND_PORT=3000 ORCHESTRATOR_BACKEND_PORT=8000 make up`

## Architecture Hotspots

- API routes: `backend/app/routes/`
- Task lifecycle/state transitions: `backend/app/services/task_state.py`
- Idempotency handling: `backend/app/routes/tasks.py`, `idempotency_keys` table
- Tool execution safety:
  - path guard: `backend/app/security/path_guard.py`
  - command policy: `backend/app/security/command_runner.py`
- PR creation flow: `backend/app/services/pr_creator.py`

## Non-Negotiables

1. Preserve task state-machine invariants.
2. Preserve owner-scoped authz checks on task operations.
3. Keep idempotent behavior for phase-changing endpoints.
4. Keep file/command tool boundaries inside worktree constraints.
5. Do not introduce raw-shell execution paths for agent tools.

## Database / Migration Rules

- If models change, add/adjust Alembic revisions under `backend/alembic/versions/`.
- Keep `alembic upgrade head` clean.
- Avoid schema drift between models and migrations.

## Quality Bar

Before finalizing changes:
1. `make backend-check`
2. `make frontend-check` (if frontend touched)
3. `make check` when changes cross backend/frontend boundaries

## PR Expectations

- Use focused, descriptive commit messages.
- Include a short validation summary (commands + outcomes).
- Mention risks/regressions explicitly (auth, state transitions, PR flow, docker runtime).
