<!--
AI Assistance Disclosure:
Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
Scope: AI-generated service README, following supplier-service/README.md.
Author review: <to be completed by author>
-->

# Service Overview
The Credit Service runs CampusRun's closed credit economy: one wallet per student with an available and a reserved
balance, credits held against open errands, and payment to the courier or refund to the requester when an errand
ends. It covers backlog requirements F12 to F14 and N5.

It has two processes built from one image:

- **credit-worker** applies every balance change. Changes arrive only as command messages on RabbitMQ, from the
  User Service (`OpenWallet`) and the Order Service (`ReserveCredits`, `AdjustReservation`, `TransferCredits`,
  `ReleaseCredits`).
- **credit-service** is a read-only HTTP API: your wallet, your credit history, an errand's reservation, and an
  admin audit. No HTTP request can change a balance.

It uses FastAPI and aio-pika with SQLAlchemy Core on a Postgres 18 database, with Alembic for migrations, like the
other services. The design, and the reasons for it, are in [docs/credit-service-plan.md](../docs/credit-service-plan.md).

# Getting started
[Install uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker Desktop first.

1. In the repo root, copy `.env.example` to `.env` and fill in `CREDIT_DB_PASSWORD`, `JWT_SECRET` and the four
   `RABBITMQ_*_PASSWORD` values (any random strings, e.g. from
   `uv run python -c "import secrets; print(secrets.token_urlsafe(24))"`).
2. In `credit-service`, copy `.env.example` to `.env` and put in the same passwords and `JWT_SECRET`.
3. Run these in `credit-service`:

| With mise | Without mise | What it does |
|---|---|---|
| `mise run credit-db` | `docker compose up -d credit-db rabbitmq` | Starts Postgres on `127.0.0.1:5435` and RabbitMQ on `127.0.0.1:5672` |
| `mise run migrate` | `uv run alembic upgrade head` | Creates or updates the tables |
| `mise run worker` | `uv run credit-worker` | Applies commands from RabbitMQ |
| `mise run serve` | `uv run fastapi dev src/credit_service/main.py --port 8003` | API at http://localhost:8003, docs at http://localhost:8003/docs |
| `mise run audit` | `uv run credit-audit` | Checks balances against the ledger; exits 1 on a problem |
| `mise run test` | `uv run pytest --cov=credit_service` | Tests, in a separate `credit_service_test` database (RabbitMQ not needed) |

To run everything in Docker instead, run `docker compose up --build` from the repo root. The API is reachable
through the gateway at http://localhost:8080/api/credits (docs at http://localhost:8080/api/credits/docs), and the
RabbitMQ management UI at http://localhost:15672 (log in with `RABBITMQ_ADMIN_USER` / `RABBITMQ_ADMIN_PASSWORD`).

## Demo before the Order Service creates errands
The Order Service currently only does AI autofill, so `credit-demo` stands in for its errand flow: it connects to
RabbitMQ as the `order-service` user, sends commands, waits for the replies and prints balances before and after.
From the repo root:

```
docker compose run --rm credit-demo register                 # two new students; watch PENDING turn into 100
docker compose run --rm credit-demo scenario 2 3 --pause     # reserve, repeat, adjust, transfer, repeat, release, refusal
docker compose run --rm credit-demo race 2 --count 50        # 50 reserves at once: never below zero
docker compose run --rm credit-demo transfer --errand 41 --requester 2 --courier 3 --no-wait   # queue it while the worker is stopped
docker compose run --rm credit-demo balances 2 3
docker compose run --rm credit-demo audit
```

## Changing the tables
Edit `src/credit_service/tables.py`, then create a migration, review it, and apply it:

```
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

`tests/test_api.py::test_migrations_match_tables` fails if `tables.py` and the migrations disagree.

# Messages
Commands go to exchange `credit.commands` with the routing key below; replies come back on exchange
`credit.replies` with routing key = the sender (bound to queue `order-service.credit-replies`). Bodies are camelCase
JSON; `type`, `message_id` and `user_id` (the sender's RabbitMQ login) are AMQP properties. Full contract:
[`commands.py`](src/credit_service/commands.py).

| Command | Routing key | Only from | Body | Effect |
|---|---|---|---|---|
| `OpenWallet` | `wallet.open` | user-service | `userId` | Wallet with `INITIAL_CREDITS` (100), once per user. No reply. |
| `ReserveCredits` | `reservation.reserve` | order-service | `errandId`, `requesterId`, `amount` | available → reserved, once per errand |
| `AdjustReservation` | `reservation.adjust` | order-service | `errandId`, `requesterId`, `amount`, `revision` | Changes the held amount (reward amended); older revisions are ignored |
| `TransferCredits` | `reservation.transfer` | order-service | `errandId`, `requesterId`, `courierId` | Requester's reserved → courier's available |
| `ReleaseCredits` | `reservation.release` | order-service | `errandId`, `requesterId`, `reason` (`CANCELLED`/`EXPIRED`) | reserved → available |

Every reservation command gets a `ReservationResult` reply: `errandId`, `status` (`HELD`, `TRANSFERRED`,
`RELEASED`, `REJECTED`, or null if nothing was ever reserved), `amount`, `revision`, `courierId`, `reason`, and
`rejection` (why this command changed nothing, or null). Every command is idempotent: sending it again changes
nothing and returns the same result.

Messages that are malformed, from the wrong sender, or contradict the data go to the dead-letter queue
`credit-service.commands.dead` (visible in the management UI).

# API
JSON uses camelCase. Paths are relative to the service; behind the gateway they're under `/api/credits`.

| Method and path | Who | What |
|---|---|---|
| `GET /health` | anyone | Liveness and database check |
| `GET /wallets/me` | signed in | `status` (`ACTIVE`, or `PENDING` while the wallet is being opened), `available`, `reserved`, `total` |
| `GET /wallets/me/transactions` | signed in | Your ledger entries, newest first. `errandId`, `limit` (1–100, default 20), `offset` |
| `GET /reservations/{errandId}` | the errand's requester or courier, or an admin | The credits held for the errand and what happened to them; 404 for anyone else |
| `GET /admin/audit` | admin | Balances re-derived from the ledger, conservation of credits, and holds older than `STALE_HOLD_HOURS` |

There is deliberately no endpoint that changes a balance (F14.1.1).
