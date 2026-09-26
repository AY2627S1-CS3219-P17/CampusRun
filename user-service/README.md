<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-assisted Markdown formatting, environment variable setup instructions, and the full-stack build step.
Author review: Originally written and then verified by Nathan
-->

# Service Overview
The User Service manages user registration, authentication, profile information, and a user’s ability to participate as both a requester and a courier; as well as admin accounts.

It uses FastAPI with SQLAlchemy Core to handle SQL queries with a Postgres 18 database.

# Prerequisites
Ensure that [Docker](https://docs.docker.com/get-started/get-docker/) is installed and running. I recommend [uv](https://docs.astral.sh/uv/getting-started/installation/) + [mise](https://mise.jdx.dev/installing-mise.html) for package management and python versioning + scripts, but just make sure you have your virtual environment set up and activated with packages installed.

# Getting started

## Local development

### 1. Set up environment variables
Copy the project-level [.env.example](../.env.example) to [.env](../.env) and fill in `USER_DB_PASSWORD`. Compose reads this to create the database container.

Then copy the service-level [.env.example](.env.example) to [.env](.env) and put the same password in `DATABASE_URL`. The server and Alembic read this when running on your machine.

### 2a. All-in-one mise script:

```sh
mise run serve
```

This starts the local user-service db (in a Docker container), runs migrations, then starts the FastAPI server (not in a container). Use this for quick reloads during development.

### 2b. Without mise:

First, start the containerised user-service database:

```sh
docker compose up -d user-db
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

## Full build testing

### 1. Environment variables

If you haven't already, copy the project-level [.env.example](../.env.example) to [.env](../.env) and fill in `USER_DB_PASSWORD`.

### 2. Build and run the full stack

This builds the images and runs the database, migrations and server all in containers:

```sh
docker compose up --build
```

The `--build` flag rebuilds the images so your latest code changes are included. The API is then served at http://localhost:8001.