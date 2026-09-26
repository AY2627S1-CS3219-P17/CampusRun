<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-assisted Markdown formatting, environment variable setup instructions, the full-stack build step, the interactive API docs section (including the ENABLE_DOCS note), the initial admin setup section, and the running tests section.
Author review: Originally written and then verified by Nathan
-->

# Service Overview
The User Service manages user registration, authentication, profile information, and a user’s ability to participate as both a requester and a courier; as well as admin accounts.

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

The `create-initial-admin` command creates the first admin account from `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`. It only runs against an empty `admins` table, so it's safe to re-run and does nothing once any admin exists. Run it after migrations.

- **Local development:** set both variables in `user-service/.env`, then run:

  ```sh
  mise run create-admin
  ```

  This starts the database and applies migrations first. Without mise, run `uv run create-initial-admin` once migrations are applied.

- **Full stack (Compose):** the variables aren't passed to the containers, so provide them on the command line. This reuses the one-off `user-migrate` container, so the password never enters the long-running server's environment:

  ```sh
  docker compose run --rm -e INITIAL_ADMIN_USERNAME=<username> -e INITIAL_ADMIN_PASSWORD=<password> user-migrate create-initial-admin
  ```

## Running tests

Make sure Docker is running, then:

```sh
mise run test
```

Or without mise, `uv run pytest`. The tests start a throwaway Postgres 18 container (via Testcontainers) and create fresh tables for each test, so they never touch your local development database.

## Interactive API docs

FastAPI generates live documentation from the code, so it always matches the running server. It's served on whichever port you're using (`8000` locally, `8001` with Compose) as long as `ENABLE_DOCS=true` is set. It's set in `.env.example` and `compose.yaml`, and off by default, so deployed environments don't publish the API schema:

- **`/docs`:** Swagger UI. Lists every endpoint with its parameters and response shapes. Use **Try it out** to send real requests to the running server, which is useful for testing endpoints without writing `curl` commands.
- **`/redoc`:** the same information as read-only reference documentation.
- **`/openapi.json`:** the raw OpenAPI schema, for tools such as frontend client generators.
