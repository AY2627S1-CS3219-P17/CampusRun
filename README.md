<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
Scope: AI-written "Gateway, root paths and API docs" section and AI Use Summary bullets; the rest was written by the team.
Author review: <to be completed by author>
-->

# CS3219 — Software Design and Architecture (AY2627 Sem 1)

## CampusRun

**CampusRun** is a peer-to-peer campus errand platform where
students can request items to be collected from stores or facilities on
campus, and other students can fulfil (and deliver) those requests. The
platform runs on a closed credit economy — credits cannot be bought,
withdrawn, or exchanged for money, and only circulate within the platform.

---

## Running the project

Local service-specific development can be done with a service-level .env file, where environment variables like the local database URL is provided.

The local database can be run using the service-specific database service in the project-level [`compose.yaml`](compose.yaml). For example, to run the user-service database: `docker compose up -d user-db`

To run the entire project locally, use `docker compose up` with [`compose.yaml`](compose.yaml), where the env vars overwrite those in the service-level .env file.

For cloud deployments, separate configuration will be required.

### Gateway, root paths and API docs

- **One entry point.** Browsers reach every service through a single nginx gateway ([`gateway/nginx.conf`](gateway/nginx.conf)) at http://localhost:8080. It's the only container published on the host. The services are reachable only on the Compose private network, by service name (e.g. `http://user-service:8000`). The databases are also published, but bound to `127.0.0.1` for host tooling. The reasoning is in [`docs/auth-plan.md`](docs/auth-plan.md).
- **Routing.** `/api/users/...` goes to user-service and `/api/suppliers/...` to supplier-service; every other path goes to the `frontend` container, which serves the built web app. So the app runs at http://localhost:8080 and calls the API on the same origin, with relative `/api/...` URLs. For the API routes, nginx strips the prefix, so each service defines its routes relative to its own root and doesn't repeat its name: `GET /api/suppliers/{id}` is `GET /{id}` in supplier-service.
- **Root paths.** The services never see the prefix, so each one reads a `ROOT_PATH` setting (e.g. `/api/users`, set in `compose.yaml`) and passes it to FastAPI's `root_path`. That keeps the docs pages, the OpenAPI schema and any URLs a service builds itself (such as `Location` headers) pointing at the gateway path. Leave it empty when running a service directly on your machine.
- **Opt-in API docs.** `/docs`, `/redoc` and `/openapi.json` are off unless `ENABLE_DOCS=true`. `compose.yaml` and each service's `.env.example` turn them on for local development; deployed environments leave the setting unset, so they don't publish the API schema. Through the gateway, the docs are at `http://localhost:8080/api/<service>/docs`.
- **Adding a service:**
  1. Add a `location /api/<service>/` block to `gateway/nginx.conf`.
  2. Set `ROOT_PATH` and `ENABLE_DOCS` for the service in `compose.yaml`.
  3. Add the service to the gateway's `depends_on`.
  4. If the service has a route at its root (like the supplier list), also add an exact-match `location = /api/<service>` block. Otherwise a request without the trailing slash, e.g. `/api/<service>?q=...`, gets a 404.

## Team Members

| Name | Role |
| ----- | ----- |
| Nathan Tew | User Service, Gateway |
| Aaron Rodrigues | Supplier Service |
| Your Name | Your ownership |

---

## Repository Structure

This repository follows a **one-service-per-folder** structure: each
microservice (`user-service/`, `supplier-service/`, `order-service/`,
`credit-service/`) lives in its own top-level folder.

```text
.
├── user-service/
├── supplier-service/
├── order-service/
├── credit-service/
├── <n2h-service>/
└── README.md
```

- Any **nice-to-have (N2H)** feature that warrants its own service should
  be added as an **additional folder** at the same level, following the
  same per-service structure.
- Files for agentic coding tools (e.g. agent configs, prompts, skills)
  may be added as needed, but must still **respect the
  one-service-per-folder skeleton** for core implementation.

---

## AI Use Summary

**Tools:** Claude Code (model: Claude Opus 5.5)

**Decisions made by the team before AI assistance:** FastAPI with SQLAlchemy Core for the user service; a `users` table with an auto-increment integer id; a separate admin table.

**Used for:**
- **Explaining** implementation order (tables → Alembic → FastAPI), Docker Compose networking and service-name DNS, environment variable handling (`pydantic-settings` precedence, root vs. service `.env`), Docker layer caching with uv, and how a Compose setup differs from a Google Cloud Run deployment.
- **Suggesting** separate admin accounts (their own credentials, not a foreign key to `users`), which the team adopted, plus case-insensitive unique indexes on email and username.
- **Suggesting** a local Compose layout (separate `user-db`, `user-migrate` and `user-service` containers). This was an AI suggestion; the AI retracted its initial claim that a separate migration service is "standard practice" after being asked for documentation.
- **Generating** boilerplate for the user service: root `compose.yaml` and `.env.example` entries, `user-service/Dockerfile`, `user-service/.dockerignore`, `user-service/.env.example`, `src/user_service/{config,db,main}.py` (settings, database engine and `GET /health`), and `src/user_service/tables.py` (the `users` and `admins` table definitions, to the team's column spec). The AI also added the `pydantic-settings` dependency to `user-service/pyproject.toml`.
- **Configuring** Alembic (after the team ran its async template): `user-service/migrations/env.py` reads `DATABASE_URL` from the app settings and uses the tables' metadata for autogenerate. The placeholder URL was removed from `user-service/alembic.ini`.
- **Debugging** type-checker warnings: a targeted Pyright ignore on `Settings()` in `config.py`, and the `lifespan` return type in `main.py` changed to `AsyncGenerator`.
- **Generating** the `user-migrate` Compose service (a one-off `alembic upgrade head` that `user-service` waits for), and **explaining** the autogenerate workflow, image rebuilds (`--build`), and host vs. Compose development. The mise tasks and `user-service/README.md` were written by the team and reviewed by the AI; the AI added the README's interactive API docs section.
- **Suggesting and generating** initial admin seeding: a `create-initial-admin` uv project script (`src/user_service/scripts/create_admin.py`) that creates the first admin from `INITIAL_ADMIN_*` settings only when the `admins` table is empty, a `create-admin` mise task wrapping it, a shared Argon2 hasher (`src/user_service/security.py`, adding the `pwdlib[argon2]` dependency), and the matching README section. The team chose to supply the initial credentials via environment variables; the AI recommended a one-off command over an Alembic data migration or app-startup hook.
- **Generating** tests for the admin seeding script (`user-service/tests/`), using pytest with a throwaway Postgres container (Testcontainers) so tests never touch development data, plus a `test` mise task. The test database is built by running the Alembic migrations (via a caller-supplied connection added to `migrations/env.py`), and a test fails if `tables.py` and the migrations drift apart.
- **Completing** the team's draft registration endpoint as `POST /auth/register`: request/response models (`src/user_service/schemas.py`) that validate NUS emails, usernames and password length; hashing in a worker thread; a race-safe insert that returns 409 with a message that doesn't reveal which field is taken; committing the per-request transaction before the response is sent (`db.py`); and endpoint tests (`tests/test_register.py`). The team approved the AI's proposed field rules; the AI chose the non-revealing 409 message for privacy.
- **Explaining** FastAPI's auth building blocks and the options for authenticating across microservices (gateway, JWT verification in each service, event-driven account creation), then **generating** a step-by-step guide (`docs/auth-plan.md`) for an nginx gateway and JWT login in the user service. The team chose the gateway and decided that the requester/courier toggle is a UI mode only; the AI proposed a `type` claim to tell users and admins apart, since the two tables share ids.
- **Debugging and linking up** the gateway: explaining where the service hostnames and ports come from (Compose service names and each Dockerfile's start command), and finding that `user-service` crashed at startup because its JWT settings were set on `user-db` instead. For supplier-service, the AI pointed the web client at the gateway, removed the service's `/suppliers` route prefix at the team's request, added `ROOT_PATH` and opt-in docs to match user-service, and added an nginx exact-match route for `/api/suppliers`. It then documented the gateway conventions in this README and `AGENTS.md`.

**Verification:** `GET /health` and settings loading were checked in-process against an unreachable database and a missing `DATABASE_URL`. <!-- TODO(author): describe your own review and testing of the AI outputs -->

### Supplier Service (Aaron)

**Tools:** Claude (claude.ai chat, model: Claude Opus 5.5)

**Decisions made by the team before AI assistance:** FastAPI with SQLAlchemy Core and PostgreSQL; one service per folder with its own database; the user-service conventions (Alembic, config, Dockerfile); and the web client's supplier fields and types.

**Used for:**
- **Suggesting** Implementation support and code review for the supplier service, including:
- **Preparing** the supplier seed data in supplier-service/seed/suppliers.csv, as well as seed/delivery-locations.csv and scripts/demo-supplier.json. These files do not contain header comments.
- **Reviewing** and aligning the supplier service after the web client and user service were added, particularly around shared conventions and interfaces.
- **Debugging** and verification of transaction behaviour. Testing showed that FastAPI 0.141 can send a response before a yield dependency's transaction is committed; the service therefore uses Depends(..., scope="function") so that the transaction is committed before the response is returned.
- **Clarifying** and documenting design decisions recorded in supplier-service/DESIGN.md.

**Verification:** The service was tested against PostgreSQL, including 58 automated tests with 94% coverage, and the API was exercised end-to-end over HTTP after migrating and seeding a fresh database. Docker image builds were not performed because Docker was unavailable. <!-- TODO(author): describe your own review and testing -->

**Files affected:** each carries an "AI Assistance Disclosure" header comment.

**Prompts and key exchanges:** see [`ai/usage-log.md`](ai/usage-log.md).