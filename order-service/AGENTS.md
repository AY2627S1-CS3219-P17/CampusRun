<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
Scope: AI-generated agent notes for the order service, following credit-service/AGENTS.md.
Author review: <to be completed by author>
-->

# Service Overview
The Order Service owns errands and delivery locations: the errand lifecycle from OPEN to COMPLETED, CANCELLED or
EXPIRED, and the credit commands each step sends to the Credit Service. It also serves AI autofill for the create
form. FastAPI with SQLAlchemy Core (async, asyncpg) on its own Postgres database, Alembic migrations, and an aio-pika
worker. The design and the build order are in `docs/order-service-plan.md`.

# Conventions
- Two processes from one image: the HTTP API (`main.py`) and `order-worker` (`worker.py`). The API never connects to
  RabbitMQ.
- Credit commands are written to the `outbox` table in the same transaction as the change that causes them, and
  `order-worker` publishes them. Never publish from a request handler.
- Every state change is one conditional `UPDATE ... WHERE <expected state and party> RETURNING`. Zero rows means the
  change is refused (404, 403 or 409). Never decide a change from an unlocked read: a value needed before the update
  (e.g. the old reward in `edit`) is read with `FOR UPDATE`, and the `UPDATE` still carries its full guard.
- Never call another service while holding a database connection. Endpoints that call other services take `Engine`
  (not `Connection`), make those calls first, then open one short transaction (`engine.begin()`).
- Reply handling must be idempotent and acknowledge only after the transaction commits. Never `nack(requeue=True)`.
- Routers with fixed paths are included before the ones with `/{errand_id}` at the root (see `main.py`).
- JSON (HTTP and messages) is camelCase; Python is snake_case. Errors use `{"detail": ...}`, and 422 responses add
  `"errors": {field: message}` (`errors.py`).
- Responses never include another user's email address.
- Schema changes go in `tables.py` plus a new Alembic migration.
- Every AI-influenced file carries an "AI Assistance Disclosure" header (see the root `AGENTS.md`).
