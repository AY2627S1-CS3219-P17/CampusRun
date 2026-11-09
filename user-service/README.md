<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-assisted Markdown formatting, environment variable setup instructions, the full-stack build step, the interactive API docs section (including the ENABLE_DOCS note), the initial admin setup section, the running tests section, and the protecting an endpoint section (2026-09-27); AI-updated the admin and endpoint sections for the admin role, and the Compose seeding step (2026-09-28); AI-updated them so admins keep student capabilities (2026-09-28).
Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
Scope: AI-written "Opening the user's wallet" section.
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
Scope: AI-added the internal endpoints section and the 401 messages.
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
Scope: AI-added the managing admins section.
Author review: Originally written and then verified by Nathan
-->

# Service Overview
The User Service manages user registration, authentication, profile information, and a user’s ability to participate as both a requester and a courier. Admins are users with the `admin` role: they sign in the same way and keep every student capability, plus admin permissions such as managing suppliers.

It uses FastAPI with SQLAlchemy Core to handle SQL queries with a Postgres 18 database.

# Prerequisites
- Ensure that [Docker](https://docs.docker.com/get-started/get-docker/) is installed and running. 
- This project uses Python 3.14.7. I recommend [uv](https://docs.astral.sh/uv/getting-started/installation/) + [mise](https://mise.jdx.dev/installing-mise.html) for package management and python versioning + scripts.
- If you choose not to use `uv`, just make sure you have your virtual environment set up and activated with packages installed.

# Getting started

## Local development

Run all commands from the `user-service/` directory.

### 1. Set up environment variables
Copy the project-level [.env.example](../.env.example) to `.env` and fill in `USER_DB_PASSWORD`. Compose reads this to create the database container.

Then copy the service-level [.env.example](.env.example) to `user-service/.env` and put the same password in `DATABASE_URL`. The server and Alembic read this when running on your machine.

### 2a. All-in-one mise script

```sh
mise run serve
```

This starts the local user-service db (in a Docker container), runs migrations, then starts the FastAPI server (not in a container). Use this for quick reloads during development.

### 2b. Without mise

First, start the containerised user-service database:

```sh
docker compose up -d --wait user-db
```

Next, run migrations:

```sh
uv run alembic upgrade head
```

Then, start the server:

```sh
uv run fastapi dev src/user_service/main.py
```

- **Not using `uv`?** Make sure your virtual env is activated with packages installed, then omit `uv run` from both commands:

  ```sh
  alembic upgrade head
  fastapi dev src/user_service/main.py
  ```

### 3. Usage
The API is then served at http://localhost:8000, with interactive docs at http://localhost:8000/docs (see [Interactive API docs](#interactive-api-docs)).

## Full build testing

### 1. Environment variables

If you haven't already, copy the project-level [.env.example](../.env.example) to `.env` and fill in `USER_DB_PASSWORD`.

### 2. Build and run the full stack

This builds the images and runs the database, migrations and server all in containers:

```sh
docker compose up --build
```

The `--build` flag rebuilds the images so your latest code changes are included. The API is then served at http://localhost:8001, with interactive docs similarly at http://localhost:8001/docs.

## Creating the initial admin

The `create-initial-admin` command creates the first admin (a user with the `admin` role) from `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`. These follow the same rules as registration, so the email must be an `@u.nus.edu` address. It does nothing once any admin exists, so it's safe to re-run. It fails if a student already uses the email or username. Run it after migrations. Registration always creates students. After that, admins promote other users through the API (see [Managing admins](#managing-admins)).

- **Local development:** set all three variables in `user-service/.env`, then run:

  ```sh
  mise run create-admin
  ```

  This starts the database and applies migrations first. Without mise, run `uv run create-initial-admin` once migrations are applied.

- **Full stack (Compose):** set all three variables in the **root** `.env`, then run `docker compose up`. The one-off `user-seed-admin` container runs `create-initial-admin --skip-if-unset` after migrations. It skips if the variables are empty, and exits once it's done. `user-service` doesn't wait for it, and the password never enters the long-running server's environment. Check the result with `docker compose logs user-seed-admin`. To re-run it after changing the variables:

  ```sh
  docker compose run --rm user-seed-admin
  ```

## Managing admins

Admin-only endpoints for the web app's admin page (`src/user_service/admin.py`):

| Endpoint | What it does |
| --- | --- |
| `GET /admin/users?q=&role=&page=&page_size=` | Searches users by username or email. Returns id, username, email and role only. |
| `POST /admin/users/{user_id}/promote` | Makes a student an admin. `404` if there's no such user, `409` if they're already an admin. |
| `POST /admin/me/step-down` | Gives up your own admin role. `409` if you're the only admin left. |

An admin can't demote anyone else, so there's always at least one admin and no admin can lock another out.

Two safeguards protect these endpoints:

- **Role changes run one at a time.** Each change takes a Postgres transaction-level advisory lock (`pg_advisory_xact_lock`) first. Without it, the last two admins stepping down at the same moment would each count two admins, and both would succeed, leaving none.
- **The caller's role is re-checked in the database,** inside the lock. The role in an access token can be up to `JWT_ACCESS_TOKEN_TTL_SECONDS` old. Without the re-check, an admin who just stepped down could use their old token to promote themselves straight back. A `403` is returned instead.

Sessions don't end on a role change. `/auth/refresh` reads the role from the database, so the new role reaches the user's next access token, at most `JWT_ACCESS_TOKEN_TTL_SECONDS` (5 minutes) later. Until then, a demoted admin's old token still passes the role checks in the other services. Each change is logged with the acting admin's id and the target's id.

## Opening the user's wallet

Every new user needs a credit wallet with the initial credits. Registration (and `create-initial-admin`) inserts an `OpenWallet` message into the `outbox` table **in the same transaction** as the user, so either both are saved or neither is. A background task in the server (`OutboxRelay` in `outbox.py`) then publishes it to RabbitMQ every `OUTBOX_POLL_SECONDS` (1s) and marks it published once RabbitMQ confirms it. The credit service opens the wallet; until then the web app shows the wallet as pending.

- **RabbitMQ is down:** registration still succeeds. The message waits in the outbox, and the relay retries with backoff (up to 30s apart) until it gets through. `SELECT message_type, attempts, last_error FROM outbox WHERE published_at IS NULL` shows what's waiting.
- **Sent twice** (e.g. a crash after publishing but before marking it): harmless, because the credit service ignores `OpenWallet` for a user who already has a wallet.
- **Repairs:** `uv run resync-wallets` (or `docker compose run --rm user-service resync-wallets`) queues `OpenWallet` for every user. Use it if the credit database was restored from an older backup. The migration that added the outbox did this once for users who registered before it.

## Protecting an endpoint

To require a login, add a `CurrentUser` or `CurrentAdmin` parameter (from `user_service.auth`) to the endpoint:

```python
@app.get("/users/me")
async def read_current_user(account: CurrentUser, conn: Connection) -> UserResponse:
    ...  # account.id is the authenticated user's ID
```

FastAPI looks at the parameter's **type**, not its name, so `account` could be called anything. `CurrentUser` is `Annotated[Account, Depends(require_user)]`, which makes FastAPI run `require_user` before the endpoint. `require_user` reads the `Authorization: Bearer <token>` header and checks the JWT:

- A missing, invalid or expired token gets a `401`, with "Your session has expired. Sign in again." or "Your session is not valid. Sign in again." (the same wording as the other services). A token whose `role` isn't `student` or `admin` is invalid.
- Otherwise the endpoint runs, with `account` set to the decoded `Account(id, role)`.

`CurrentUser` accepts any role, since an admin can do everything a student can. `CurrentAdmin` runs the same checks, then also requires the token's `role` claim to be `admin`. A student's token on a `CurrentAdmin` route gets a `403`. There's deliberately no student-only dependency.

> **Warning:** nothing marks an endpoint as public. **If you leave out the parameter, anyone can call the endpoint.** Only login, registration, password-recovery start and `/health` should be unprotected.

## Internal endpoints

Paths under `/internal/` are for other services only. The gateway answers `/api/users/internal/...` with a 404, so browsers can't reach them; services call user-service directly on the Compose network (`http://user-service:8000`).

- `GET /internal/usernames?ids=1&ids=2` (signed in; up to 100 ids): `[{"id": 1, "username": "alice"}, ...]`, ordered by id, with unknown ids left out. It never returns email addresses. The Order Service uses it to show requester and courier names on errands, forwarding the signed-in user's token.

## Running tests

Make sure Docker is running, then:

```sh
mise run test
```

Or without mise, `uv run pytest`. The tests start a throwaway Postgres 18 container (via Testcontainers), build the schema by running the Alembic migrations, and empty the tables before each test, so they never touch your local development database. They also fail if `tables.py` and the migrations drift apart, so generate a migration whenever you change a table.

## Interactive API docs

FastAPI generates live documentation from the code, so it always matches the running server. It's served on whichever port you're using (`8000` locally, `8001` with Compose) as long as `ENABLE_DOCS=true` is set. It's set in `.env.example` and `compose.yaml`, and off by default, so deployed environments don't publish the API schema:

- **`/docs`:** Swagger UI. Lists every endpoint with its parameters and response shapes. Use **Try it out** to send real requests to the running server, which is useful for testing endpoints without writing `curl` commands.
- **`/redoc`:** the same information as read-only reference documentation.
- **`/openapi.json`:** the raw OpenAPI schema, for tools such as frontend client generators.
