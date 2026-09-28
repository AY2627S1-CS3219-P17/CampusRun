<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-assisted Markdown formatting, environment variable setup instructions, the full-stack build step, the interactive API docs section (including the ENABLE_DOCS note), the initial admin setup section, the running tests section, and the protecting an endpoint section (2026-09-27); AI-updated the admin and endpoint sections for the admin role, and the Compose seeding step (2026-09-28); AI-updated them so admins keep student capabilities (2026-09-28).
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

The `create-initial-admin` command creates the first admin (a user with the `admin` role) from `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`. These follow the same rules as registration, so the email must be an `@u.nus.edu` address. It does nothing once any admin exists, so it's safe to re-run. It fails if a student already uses the email or username. Run it after migrations. Registration always creates students, and no endpoint changes a user's role.

- **Local development:** set all three variables in `user-service/.env`, then run:

  ```sh
  mise run create-admin
  ```

  This starts the database and applies migrations first. Without mise, run `uv run create-initial-admin` once migrations are applied.

- **Full stack (Compose):** set all three variables in the **root** `.env`, then run `docker compose up`. The one-off `user-seed-admin` container runs `create-initial-admin --skip-if-unset` after migrations. It skips if the variables are empty, and exits once it's done. `user-service` doesn't wait for it, and the password never enters the long-running server's environment. Check the result with `docker compose logs user-seed-admin`. To re-run it after changing the variables:

  ```sh
  docker compose run --rm user-seed-admin
  ```

## Protecting an endpoint

To require a login, add a `CurrentUser` or `CurrentAdmin` parameter (from `user_service.auth`) to the endpoint:

```python
@app.get("/users/me")
async def read_current_user(account: CurrentUser, conn: Connection) -> UserResponse:
    ...  # account.id is the authenticated user's ID
```

FastAPI looks at the parameter's **type**, not its name, so `account` could be called anything. `CurrentUser` is `Annotated[Account, Depends(require_user)]`, which makes FastAPI run `require_user` before the endpoint. `require_user` reads the `Authorization: Bearer <token>` header and checks the JWT:

- A missing, invalid or expired token gets a `401`.
- Otherwise the endpoint runs, with `account` set to the decoded `Account(id, role)`.

`CurrentUser` accepts any role, since an admin can do everything a student can. `CurrentAdmin` runs the same checks, then also requires the token's `role` claim to be `admin`. A student's token on a `CurrentAdmin` route gets a `403`. There's deliberately no student-only dependency.

> **Warning:** nothing marks an endpoint as public. **If you leave out the parameter, anyone can call the endpoint.** Only login, registration, password-recovery start and `/health` should be unprotected.

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
