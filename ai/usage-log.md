# AI Usage Log

Exact prompts and key responses from AI-assisted sessions, in chronological order.

---

## Session 1 — 2026-09-25 — user-service setup

- **Tool:** Claude Code (model: Claude Opus 5.5)
- **Author:** nathantew14
- **Modes:** explain, generate
- **Timestamps:** only the date was recorded for this session; individual prompt times were not captured.
- **Decisions made before the session (by the team, not AI):** FastAPI with SQLAlchemy Core; a `users` table with an auto-increment integer id; a separate admin table.

### 1. Where to start implementing (explain)

```text
so we've decided on FastAPI with SQLAlchemy Core; a user table with auto-increment integer id, and a separate admin table. where would i start implementing all of this? schema migration? SQLAlchemy model? the first FastAPI endpoint?
```

**Key response:** Suggested this order: run Postgres and add config, define Core `Table` objects on a shared `MetaData` (with `Identity()` ids and a naming convention), set up Alembic with autogenerate, wire an `AsyncEngine` into FastAPI via `lifespan`, add `GET /health`, then `POST /users` with password hashing and tests. Raised an open question for the team: are admins separate accounts, or a role table referencing `users.id`?

### 2. Containerising the service and env var strategy (explain)

```text
how do i set it up from the start to use docker to containerise the whole service?

also, should we use service-level or project-level env vars? if i containerise the postgres database with the user api service itself, what would the database url look like?
```

**Key response:** Recommended running the API and Postgres as separate containers in one Compose project. The URL format is `postgresql+asyncpg://user:pass@user-db:5432/dbname`, where the hostname is the Compose service name. Suggested a single root `.env` with prefixed per-service values, with `compose.yaml` passing each container only the variables it needs under generic names like `DATABASE_URL`. Proposed a uv-based Dockerfile, a `.dockerignore`, and a `compose.yaml` with `user-db`, `user-migrate` and `user-service`.

### 3. Containers and hostname resolution (explain)

```text
1. does your suggested compose.yaml already have 3 separate containers? a user-db, a user-migrate, and a user-service? 
2. where is the hostname defined? it seems to be hardcoded to user-db? is that how it works when the containers are deployed with the same Compose project, no matter where the Compose project is ultimately deployed?
```

**Key response:** Confirmed three containers, with `user-migrate` as a one-off that exits after migrating. Explained that the hostname comes from the service key and is resolved by Docker's DNS on the project's default network. This works wherever Compose runs, but not on platforms like Cloud Run or Kubernetes, which is why the URL is supplied through an env var.

### 4. Migration service practice, single host, `DATABASE_URL` location (explain)

```text
1. is using a separate service just to run the migrations a standard practice? can you point me to some documentation that recommends this?
2.a) "A laptop, a teammate's machine, or a cloud VM running docker compose up all get the same private network and the same DNS names." - does that mean that in the current setup, all the services would run on the same machine/vm?
2.b) "That's why the app reads DATABASE_URL from the environment and never contains user-db itself. Only the Compose file mentions user-db, so moving to another platform means giving the app a different DATABASE_URL, with no code changes." - i don't see "DATABASE_URL" in either Dockerfile or compose.yaml that you suggested; where does DATABASE_URL come in?
```

**Key response:** Retracted the earlier claim that a separate migration service is "standard practice". No official documentation recommends it specifically; cited the Docker Compose startup-order docs (`service_completed_successfully`), Twelve-Factor XII (admin processes) and Kubernetes init containers as related sources. Offered migrating in the startup command as a simpler alternative. Confirmed that plain Compose runs on a single host. Explained that `DATABASE_URL` was in `compose.yaml` but hidden behind a YAML anchor, and suggested dropping the anchor.

### 5. Why containerise, and Cloud Run differences (explain)

```text
2a. if everything is run on one machine, what's the point of containerising? if we intend to eventually use some cloud deployment like google cloud run, what would be different?
2b. so am i right to say that the database url's hostname is currently hardcoded to use "user-db", which assumes a plain `docker compose up` deployment with everything running on one machine or VM, and sharing the same Docker private network?
```

**Key response:** Benefits of containers on one machine: reproducibility, isolation, the same image deploying anywhere, and one-command setup. Cloud Run differences: one Cloud Run service per microservice, Cloud SQL instead of a Postgres container (Cloud Run's filesystem is in-memory), a Cloud Run job for migrations, Secret Manager, and the injected `PORT`. Noted that `gcloud run compose up` deploys a single multi-container service and is aimed at development. Confirmed that `user-db` is hardcoded only in `compose.yaml`, not in the image or code.

### 6. Compose vs. future cloud setup (explain)

```text
so am i right to say that the suggested compose.yaml is separate from any cloud deplyoment setup we might do in the future, which I don't have to worry about right now?
```

**Key response:** Yes. Listed the habits to keep now so moving later only needs config: read config from env vars, listen on `$PORT`, keep no local disk state, and keep migrations as a separate command.

### 7. Must the project run under Compose? (explain)

```text
am i right to say that in your current suggested configuration, the project HAS to be run with docker compose up, or else the env vars wouldn't be supplied to the user service?
```

**Key response:** Env vars can come from Compose, `docker run -e`, the shell, a `.env` file or Cloud Run config. With the setup as it stood, running outside Compose would fail with a missing `DATABASE_URL`. Suggested a git-ignored `user-service/.env` loaded by `pydantic-settings` for running the API on the host.

### 8. Env var vs. `.env` precedence (explain)

```text
> Real environment variables take priority over the .env file

---

where is this set?
```

**Key response:** It is the `pydantic-settings` default source order (init kwargs > environment variables > dotenv > secrets directory > defaults), which can be changed with `settings_customise_sources`.

### 9. Local development database (explain)

```text
so for local dev i would still create a local db and supply that db url in a .env file at the user-service directory?
```

**Key response:** No separate install is needed: run only the Compose `user-db` container and point `user-service/.env` at `localhost:5433`. Described two modes, the full stack in Docker and the API on the host. Noted that the dev password is duplicated across the two `.env` files.

### 10. Summary (explain)

```text
give me a summary of the steps discussed so far
```

**Key response:** A consolidated plan covering Docker/Compose, env vars, tables, Alembic, FastAPI wiring, endpoints and tests, with the admin-table design still open.

### 11. Dockerfile (generate)

```text
write the dockerfile
```

**Key response:** Generated `user-service/Dockerfile` (`python:3.14.7-slim`, uv pinned to 0.12.7, a cached dependency layer, a non-root user, `CMD` using `${PORT:-8000}`) and `user-service/.dockerignore`. The build was not verified because the Docker daemon was not running.

### 12. venv path (explain)

```text
guides online typically show `ENV PATH="/venv/bin:$PATH"`. why is ours different?
```

**Key response:** `uv sync` creates `.venv` in the project directory (`/app/.venv`). Guides that use `/venv` create it there explicitly. A venv outside `/app` avoids being hidden when the source is bind-mounted; `UV_PROJECT_ENVIRONMENT=/venv` was offered as an optional change.

### 13. Two `uv sync` steps (explain)

```text
why does `uv sync` need to be run twice
```

**Key response:** Docker layer caching: the first sync installs only third-party dependencies and stays cached until `uv.lock` changes. The second installs the project package itself, which is fast.

### 14. FastAPI app, config and health check (generate)

```text
add the fastapi main, config and health
```

**Key response:** Ran `uv add pydantic-settings`. Generated `src/user_service/config.py` (`Settings` with `database_url: SecretStr`), `src/user_service/db.py` (engine factory and a per-request transaction dependency), `src/user_service/main.py` (lifespan and `GET /health`, returning 200 or 503) and `user-service/.env.example`. Verified in-process with `TestClient` against an unreachable database (503 returned) and with a missing `DATABASE_URL` (fails at startup). Not yet tested against a real database.

### 15. Attribution (generate)

```text
follow the AI attributtion guide to add any attribution required thus far
```

**Key response:** Added file-header disclosures to the AI-influenced files, this usage log, and an AI Use Summary section at the end of the root `README.md`.

### 16. Compose file (generate)

```text
update compose.yaml
```

**Key response:** Generated the root `compose.yaml` with `user-db` (Postgres 18, a named volume, a healthcheck, and a port bound to `127.0.0.1:5433`) and `user-service` (built from `./user-service`, with `DATABASE_URL` pointing at `user-db`, on port 8001). Left out `user-migrate` until Alembic is set up. Added the `USER_DB_*` placeholders to the root `.env.example`. Validated with `docker compose config`: it fails with a clear message when `USER_DB_PASSWORD` is unset and interpolates correctly when it is set. The containers were not started, because the Docker daemon was not running.

---

## Session 2 — 2026-09-25 — user and admin tables

- **Tool:** Claude Code (model: Claude Opus 5.5)
- **Author:** nathantew14
- **Modes:** explain, generate
- **Timestamps:** only the date was recorded for this session; individual prompt times were not captured.
- **Summary:** Settled the admin table design, generated the `users` and `admins` table definitions, explained the naming convention and index names, and added email verification to the schema.

### 1. Admin table design (explain)

```text
should i have a separate admin table
```

**Key response:** Pointed out that the team had already chosen a separate table, so the open question was its shape. Recommended separate admin accounts with their own credentials rather than a role table referencing `users.id`, because `user-service/README.md` describes admins as their own kind of account. Reasons given: `user_id` in other services always means a student, a compromised student account can't be escalated to admin, and admins can be created without public registration. Costs noted: a second login path, and ids that overlap between the two tables, so tokens need a role claim.

### 2. Table definitions (generate)

```text
i updated ai attribution instructions in @AGENTS.md ; take a look

next, generate the user and admin tables

user: Identity() PK, email address, username, password hash, an optional profile picture, created_at, updated_at
admin: Identity() PK, username, password hash, created_at, updated_at
```

**Key response:** Generated `src/user_service/tables.py`: a `MetaData` with a naming convention, and the `users` and `admins` tables as specified. Choices the AI made: case-insensitive unique indexes on `lower(email)` and `lower(username)`, `String(254)` for email and `String(32)` for username, a nullable `profile_picture_url` (a URL or storage key, not the image), and timezone-aware timestamps defaulting to `now()`. Verified by compiling the tables to Postgres SQL; not yet run against a database. Updated step 3 of `docs/user-service-setup.md` and the AI Use Summary in `README.md`.

### 3. Naming convention (explain)

```text
explain these lines
```

(Selected: the `MetaData(naming_convention=...)` block in `tables.py`.)

**Key response:** The convention makes constraint and index names fixed and known in advance, so Alembic migrations can refer to them by name. It needs to be set before the first migration. Explained each template (`ix`, `uq`, `ck`, `fk`, `pk`). Noted that only `pk` currently applies, because the unique indexes are named explicitly.

### 4. Explicit index names (explain)

```text
why do the three lower unique indexes have explicit names instead of using the defined convention?
```

**Key response:** Confirmed by test that the convention would work, producing names like `ix_users_email`. Explicit names were chosen because a unique `Index` gets the `ix` template rather than `uq`, so the name wouldn't show that it enforces uniqueness on `lower(email)`. Also, a later plain index on `email` would get the same name. Postgres unique constraints can't contain expressions, so a unique index is required. Offered to drop the names for consistency.

### 5. Email domain restriction (explain)

```text
we want to enforce that the email addresses have a certain domain ("@u.nus.edu"). would that be done in the schema, or just a restriction upon registration?
```

**Key response:** Recommended checking at registration: Pydantic gives a clear 422 error, the allowed domain can be a config setting that changes without a migration, and the user service is the only thing that writes emails. Pointed out that a domain check doesn't prove ownership, so email verification is needed, which means an `email_verified_at` column. A `CheckConstraint` was offered as an optional extra safeguard in the database.

### 6. Email verification column (generate)

```text
yes, add email_verified_at
```

**Key response:** Added a nullable, timezone-aware `email_verified_at` column to `users` and updated `docs/user-service-setup.md`. Verified by recompiling the table to Postgres SQL.
