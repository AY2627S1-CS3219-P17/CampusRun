# User Service Setup Plan

Last updated: 2026-09-25

## Status

| # | Step | Status |
| --- | --- | --- |
| 1 | Docker & Compose | Done, except `user-migrate` (waits on step 4) |
| 2 | Environment variables | Done |
| 3 | Table definitions | Done (not yet migrated) |
| 4 | Alembic | Not started |
| 5 | FastAPI wiring | Done |
| 6 | Endpoints & tests | `GET /health` done; `POST /users` and tests not started |

Not yet verified against a real database. Docker wasn't running, so no containers have been started.

## Steps

### 1. Docker & Compose
- [x] `user-service/Dockerfile`: `python:3.14.7-slim` with uv pinned to 0.12.7. Dependencies install as a separate cached layer (`uv sync --no-install-project`), then the project itself. Runs as a non-root `app` user. `CMD fastapi run ... --port ${PORT:-8000}` (shell form).
- [x] `user-service/.dockerignore`: `.venv`, `__pycache__`, `*.pyc`, `.env`, `.env.*`, `.DS_Store`, `.pytest_cache`.
- [x] Root `compose.yaml`:
  - `user-db`: Postgres 18 with the named volume at `/var/lib/postgresql`, a `pg_isready` healthcheck, and the port bound to `127.0.0.1:5433`.
  - `user-service`: built from `./user-service`, served on host port 8001, starts after `user-db` is healthy.
- [ ] Add `user-migrate` once Alembic exists. It uses the same image, `command: ["alembic", "upgrade", "head"]`, and waits for `user-db` to be healthy. Then change `user-service` to depend on it with `condition: service_completed_successfully`.
- Write each service's `environment:` block out in full; don't use YAML anchors.

### 2. Environment variables
- [x] Root `.env` (from `.env.example`): shared values (`JWT_SECRET`, `LOG_LEVEL`) and prefixed DB values (`USER_DB_USER`, `USER_DB_PASSWORD`, `USER_DB_NAME`). Compose refuses to start if `USER_DB_PASSWORD` is empty.
- [x] `compose.yaml` builds the generic `DATABASE_URL` (`postgresql+asyncpg://…@user-db:5432/user_service`) for the container.
- [x] `user-service/.env.example`: the host-run `DATABASE_URL` pointing at `localhost:5433`. Copy it to `user-service/.env`; the password must match `USER_DB_PASSWORD`.
- [x] `src/user_service/config.py`: `pydantic-settings` `Settings` with `database_url: SecretStr`, `env_file=".env"` and `extra="ignore"`. Real env vars beat `.env` by default.
- [ ] Pass `JWT_SECRET` / `LOG_LEVEL` to the container once the code reads them.

### 3. Table definitions (`src/user_service/tables.py`)
- [x] SQLAlchemy Core `MetaData` with a naming convention, set before the first migration.
- [x] `users`: `Identity()` integer primary key, email, nullable `email_verified_at` (null until the user confirms their email), username, password hash, nullable `profile_picture_url`, `created_at`/`updated_at`. Email and username are unique regardless of case (unique indexes on `lower(...)`).
- [x] `admins`: separate accounts with their own credentials (no foreign key to `users`). `Identity()` integer primary key, username (unique regardless of case), password hash, timestamps. Ids overlap with `users.id`, so tokens need a role claim.

### 4. Alembic
- [ ] `uv add alembic`, then `alembic init -t async migrations`.
- [ ] `env.py`: `target_metadata = metadata`; read the URL from `Settings`.
- [ ] Autogenerate the first migration, review it, then apply it.
- [ ] Add the `user-migrate` Compose service (see step 1).

### 5. FastAPI wiring
- [x] `src/user_service/db.py`: `create_engine(settings)` (with `pool_pre_ping`), `get_engine`, and a `Connection` dependency that gives one transaction per request via `engine.begin()`.
- [x] `src/user_service/main.py`: `lifespan` creates the engine on startup and disposes of it on shutdown.

### 6. Endpoints & tests
- [x] `GET /health`: runs `SELECT 1`; returns 200 `{"status":"ok","database":"ok"}` or 503 `{"status":"unavailable","database":"unreachable"}`.
- [ ] `POST /users`: Pydantic request and response schemas (never return `password_hash`); hash passwords with `pwdlib[argon2]`.
- [ ] Tests: `pytest` + `httpx.AsyncClient` against a test database migrated with Alembic. The Starlette `TestClient` currently warns to use `httpx2` instead of `httpx`; deal with it here.

## Running locally
- **Full stack:** `docker compose up --build`, then `curl localhost:8001/health`.
- **Fast development:** `docker compose up -d user-db`, then `cd user-service && uv run fastapi dev src/user_service/main.py`, then `curl localhost:8000/health`.

## Decisions
- **FastAPI + SQLAlchemy Core,** an auto-increment integer `users.id`, and a separate admin table. These were decided by the team.
- **Admins are separate accounts,** not a role on `users`. Other services' `user_id` always means a student, and a compromised student account can't become an admin.
- **Migrations run as a separate one-off step,** not on app start. This is a common pattern but isn't officially documented as a recommendation. It maps directly onto a Cloud Run job later.
- **No hostnames or secrets in code or the image.** Only `compose.yaml` mentions `user-db`.
- **`compose.yaml` is for local development and demos only.** Cloud Run (Cloud SQL, Secret Manager, a Cloud Run job for migrations, the injected `PORT`) will be configured separately later.
- **Keep the app cloud-ready:** config from env, listen on `$PORT`, no local disk state, migrations as a separate command.

## Open items
- [ ] Fill in "Author review" in each AI Assistance Disclosure header and the verification `TODO(author)` in the root README.
- [ ] Decide whether to keep `__init__.py`'s placeholder `main()` and `[project.scripts]` in `pyproject.toml`.
