<!--
AI Assistance Disclosure:
Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
Scope: AI-generated agent notes for the credit service.
Author review: <to be completed by author>
-->

# Service Overview
The Credit Service owns wallets, reservations and the ledger for CampusRun's closed credit economy (backlog F12 to
F14, N5). FastAPI with SQLAlchemy Core (async, asyncpg) on its own Postgres database, Alembic migrations, and an
aio-pika worker consuming RabbitMQ.

# Conventions
- Balances change only in `ledger.py`, only from `worker.py`, only from RabbitMQ commands. Never add an HTTP endpoint
  that changes a balance, and never let another service write to this database.
- Every wallet change is one transaction that updates the wallet, the reservation and the ledger together. Every
  change writes a ledger entry; the audit re-derives balances from the ledger.
- Every command must stay idempotent by business key (wallet = user id, reservation = errand id; a reservation only
  moves forward from `HELD`). Repeats return the original result.
- Lock order is the reservation row, then wallets by ascending user id. Keep it, or concurrent transfers can deadlock.
- A new command needs: a model and `COMMANDS` entry in `commands.py` (with its allowed sender), a binding and topic
  permission in `rabbitmq/definitions.json`, a branch in `ledger.apply`, and tests.
- The worker acknowledges a message only after the transaction commits and the reply is confirmed. It never uses
  `nack(requeue=True)`: RabbitMQ 4 doesn't count those towards the delivery limit, so a bad message would loop.
- JSON (HTTP and messages) is camelCase; Python is snake_case.
- Schema changes go in `tables.py` plus a new Alembic migration.
- Every AI-influenced file carries an "AI Assistance Disclosure" header (see the root `AGENTS.md`).
