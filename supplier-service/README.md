<!--
AI Assistance Disclosure:
Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-generated service README.
Author review: <to be completed by author>
-->

# Service Overview
The Supplier Service manages the campus suppliers students can request pickups from (shops, printers and other
places) and the predefined delivery locations. It covers backlog requirements F4 to F6 and N3.

It uses FastAPI with SQLAlchemy Core on a Postgres 18 database, with Alembic for migrations, like the User Service.
uv is the package manager of choice, optionally with mise for python versioning and the tasks below.

The design and the reasons for it are in [DESIGN.md](DESIGN.md).

# Getting started
[Install uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker Desktop first.

1. In the repo root, copy `.env.example` to `.env` and fill in:
   - `SUPPLIER_DB_PASSWORD`: any password for the local database.
   - `JWT_SECRET`: 32 or more random characters, the same one the User Service uses. For example, the output of
     `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. In `supplier-service`, copy `.env.example` to `.env`. Put the same password in `DATABASE_URL` and the same
   `JWT_SECRET`.
3. Run these in `supplier-service`:

| With mise | Without mise | What it does |
|---|---|---|
| `mise run supplier-db` | `docker compose up -d supplier-db` | Starts Postgres on `127.0.0.1:5434` |
| `mise run migrate` | `uv run alembic upgrade head` | Creates or updates the tables |
| `mise run seed` | `uv run python -m supplier_service.seed` | Loads `seed/*.csv` into empty tables (safe to run again) |
| `mise run serve` | `uv run fastapi dev src/supplier_service/main.py --port 8002` | API at http://localhost:8002, docs at http://localhost:8002/docs |
| `mise run test` | `uv run pytest --cov=supplier_service` | Tests, in a separate `supplier_service_test` database |

To run everything in Docker instead, run `docker compose up --build` from the repo root. `supplier-migrate` migrates
and seeds, then `supplier-service` starts on port 8002.

## Signing in
Every endpoint except `/health` needs `Authorization: Bearer <token>`: a JWT from the User Service with `sub`,
`role` (`student` or `admin`) and `exp`. Until the User Service can sign users in, make one here:

```
uv run python scripts/make_token.py --role admin      # or --role student
```

In Swagger (`/docs`), click **Authorize** and paste the token.

## Changing the tables
Edit `src/supplier_service/tables.py`, then create a migration, review it, and apply it:

```
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

`tests/test_suppliers.py::test_migrations_match_tables` fails if `tables.py` and the migrations disagree.
Autogenerate ignores the keyword-search index (`ix_suppliers_search_trgm`), so a change to it must be written into
a migration by hand.

# API
JSON uses camelCase (`startTime`, `locationDescription`), matching `frontend/src/types/supplier.ts`.

| Method and path | Who | What |
|---|---|---|
| `GET /health` | anyone | Liveness and database check |
| `GET /meta` | signed in | Supplier types and the served-area bounds |
| `GET /suppliers` | signed in | Query options: `q`, `type` (repeatable), `building`, `openNow`, `active` (`false` for admins only), `nearLat` + `nearLng` (+ `radius`, in metres), `sort` (`name`, `-name`, `type`, `-createdAt`, `-updatedAt`, `distance`), `page`, `pageSize` |
| `GET /suppliers/buildings` | signed in | Building names, for the location filter |
| `GET /suppliers/{id}` | signed in | One supplier |
| `POST /suppliers` | admin | Create |
| `PATCH /suppliers/{id}` | admin | Change any fields; `{"active": false}` deactivates and `{"active": true}` reactivates |
| `DELETE /suppliers/{id}` | admin | Soft delete |
| `/delivery-locations` and `/delivery-locations/{id}` | same as above | Delivery locations (`q`, `active`, `page`, `pageSize`) |

A request with no token, or an invalid one, gets 401; a request whose role isn't allowed gets 403. Validation errors
return 422 with `{"detail": "...", "errors": {"fieldName": "message"}}`.

# Configuration
| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | none, required | Postgres connection (`postgresql+asyncpg://...`) |
| `JWT_SECRET` | none, required (32+ characters) | Shared with the User Service |
| `JWT_ALGORITHM` | `HS256` | Must match the User Service |
| `CORS_ORIGINS` | empty | Comma-separated browser origins allowed to call the service directly |
| `SERVED_AREA_MIN_LAT` … `SERVED_AREA_MAX_LNG` | a box around the NUS Kent Ridge campus | Where suppliers may be placed |
| `PORT` | `8000` | Port inside the container |
