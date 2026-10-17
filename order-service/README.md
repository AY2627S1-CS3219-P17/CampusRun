<!--
AI Assistance Disclosure:
Tool: OpenAI Codex (GPT-6), date: 2026-10-17
Scope: Documented the database-free AI autofill endpoint, local settings, and Groq free-plan limits.
Author review: <to be completed by author>
-->

# Order service

This service currently provides AI suggestions for the create-request form. It does not create or store errands, and it currently has no database.

## Run locally with the full app

Set `GROQ_API_KEY` in the ignored root `.env`, then run `docker compose up --build` from the repository root. The gateway exposes the service at `http://localhost:8080/api/orders`; local API docs are at `/api/orders/docs`. The service can start without the key, but autofill returns 503 until it is configured.

To run this service directly, copy `.env.example` to `.env`, set `JWT_SECRET` to the user-service signing secret and `SUPPLIER_SERVICE_URL` to the gateway supplier URL, then run `uv run --python 3.14.7 fastapi dev src/order_service/main.py`.

## Autofill

`POST /autofill` requires a user-service bearer token and JSON `{"description":"..."}` with 20–500 trimmed characters. It extracts nullable title, supplier, delivery building and floor, short description, delivery deadline, and credits. The supplier is resolved to an active supplier ID and name. Unknown or invalid suggestions return `null`. This endpoint never creates an order. The map position remains a manual selection. The `description` suggestion contains only stated details describing or locating the delivery building.

## Groq free-plan limits

For `openai/gpt-oss-120b`, Groq currently lists **30 requests/minute**, **1,000 requests/day**, **8,000 tokens/minute**, and **200,000 tokens/day** on its free plan. Limits are shared at the organization level, and your account may differ; check the [Groq rate-limits page](https://console.groq.com/docs/rate-limits) and your console Limits page for current values. A limit hit returns HTTP 429.
