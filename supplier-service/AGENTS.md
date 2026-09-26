<!--
AI Assistance Disclosure:
Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-generated agent notes for the supplier service.
Author review: <to be completed by author>
-->

# Service Overview
The Supplier Service stores and serves campus suppliers (pickup points) and delivery locations for CampusRun (backlog
F4 to F6, N3). It uses FastAPI with SQLAlchemy Core (async, asyncpg) on its own Postgres database, with Alembic
migrations, following the same structure as `user-service`. It should be containerised and deployable via docker.

# Conventions
- Schema changes go in `tables.py` plus a new Alembic migration. Migrations and seeding are separate commands, not
  part of app start-up.
- Authentication: verify the User Service's JWT locally with the shared `JWT_SECRET` (`auth.py`). Reading needs any
  signed-in user (`AnyUser`); writing needs `AdminUser`. 401 means no token or an invalid one; 403 means the wrong role.
- JSON is camelCase to match `frontend/src/types/supplier.ts`; Python uses snake_case. Supplier types are
  `Food`, `Drinks`, `Shopping`, `Printing`.
- Validate every input in `schemas.py`. Errors use `{"detail": ...}`, and 422 responses add `"errors": {field: message}`.
- One transaction per request (`db.Connection`), committed before the response is sent.
- Deleting is a soft delete (`deleted_at`), because other services keep supplier ids.
- Every AI-influenced file carries an "AI Assistance Disclosure" header (see the root `AGENTS.md`).
