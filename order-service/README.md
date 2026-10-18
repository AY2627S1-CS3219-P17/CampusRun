<!--
AI Assistance Disclosure:
Tool: OpenAI Codex (GPT-6), date: 2026-10-17
Scope: Documented the database-free AI autofill endpoint, local settings, and Groq free-plan limits.
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
Scope: Documented the database, the order-worker process, the local development commands and delivery locations.
Author review: <to be completed by author>
-->

# Order service

The Order Service will run the errand lifecycle and send the matching credit commands to the Credit Service over
RabbitMQ (see [docs/order-service-plan.md](../docs/order-service-plan.md)). It's being built step by step: so far it
has its database, migrations, the `order-worker` process, delivery locations and AI autofill for the create-request form.

It has two processes built from one image:

- **order-service**: the HTTP API. It never connects to RabbitMQ.
- **order-worker**: publishes queued credit commands, applies the credit service's replies and expires errands past
  their deadline. For now it only connects to the database and RabbitMQ and waits.

## Run locally with the full app

In the root `.env`, set `ORDER_DB_PASSWORD` (any random string) and, for autofill, `GROQ_API_KEY`. Then run
`docker compose up --build` from the repository root. The gateway exposes the service at
`http://localhost:8080/api/orders`; local API docs are at `/api/orders/docs`. The service can start without the
Groq key, but autofill returns 503 until it is configured.

`credit-demo` logs in to RabbitMQ as `order-service` and reads the same reply queue as `order-worker`. Run
`docker compose stop order-worker` before using it, or the two split the replies between them.

## Run directly on your machine

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker Desktop. Copy `.env.example` to
`.env` and fill in the passwords and `JWT_SECRET` to match the root `.env`. Then, in `order-service`:

| With mise | Without mise | What it does |
|---|---|---|
| `mise run order-db` | `docker compose up -d --wait order-db rabbitmq` | Starts Postgres on `127.0.0.1:5436` and RabbitMQ on `127.0.0.1:5672` |
| `mise run migrate` | `uv run alembic upgrade head` | Creates or updates the tables |
| `mise run serve` | `uv run fastapi dev src/order_service/main.py --port 8004` | API at http://localhost:8004, docs at http://localhost:8004/docs |
| `mise run worker` | `uv run order-worker` | Runs the background worker |
| `mise run test` | `uv run pytest --cov=order_service` | Tests, in a throwaway Postgres container (Docker must be running; RabbitMQ not needed) |

## Delivery locations

`/delivery-locations` (list, get, create, edit) holds where errands are delivered. These used to be in supplier-service.
- **Predefined** locations are the shared campus list, loaded from `seed/delivery-locations.csv` by `order-migrate`
  (`python -m order_service.seed`, safe to rerun). Everyone sees them; only admins add or edit them.
- **Personal** locations are added by a student. Only that student sees and edits them.
- A location can't be edited while an errand using it has a courier on the way (409).

## Autofill

`POST /autofill` requires a user-service bearer token and JSON `{"description":"..."}` with 20–500 trimmed characters. It extracts nullable title, supplier, delivery building and floor, short description, delivery deadline, and credits. The supplier is resolved to an active supplier ID and name. Unknown or invalid suggestions return `null`. This endpoint never creates an order. The map position remains a manual selection. The `description` suggestion contains only stated details describing or locating the delivery building.

## Groq free-plan limits

For `openai/gpt-oss-120b`, Groq currently lists **30 requests/minute**, **1,000 requests/day**, **8,000 tokens/minute**, and **200,000 tokens/day** on its free plan. Limits are shared at the organization level, and your account may differ; check the [Groq rate-limits page](https://console.groq.com/docs/rate-limits) and your console Limits page for current values. A limit hit returns HTTP 429.
