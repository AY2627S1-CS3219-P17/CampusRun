<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
Tool: OpenAI Codex (GPT-6), date: 2026-10-16; 2026-10-17
Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
Scope: AI-written "Gateway, root paths and API docs" section and AI Use Summary bullets, including the frontend AI entry view disclosure,
       the credit-service routing note and the Credit Service AI Use Summary; the rest was written by the team.
Author review: <to be completed by author>
-->

# CS3219 â€” Software Design and Architecture (AY2627 Sem 1)

## CampusRun

**CampusRun** is a peer-to-peer campus errand platform where
students can request items to be collected from stores or facilities on
campus, and other students can fulfil (and deliver) those requests. The
platform runs on a closed credit economy â€” credits cannot be bought,
withdrawn, or exchanged for money, and only circulate within the platform.

---

## Running the project

Local service-specific development can be done with a service-level .env file, where environment variables like the local database URL is provided.

The local database can be run using the service-specific database service in the project-level [`compose.yaml`](compose.yaml). For example, to run the user-service database: `docker compose up -d user-db`

To run the entire project locally, use `docker compose up` with [`compose.yaml`](compose.yaml), where the env vars overwrite those in the service-level .env file.

For cloud deployments, separate configuration will be required.

### Gateway, root paths and API docs

- **One entry point.** Browsers reach every service through a single nginx gateway ([`gateway/nginx.conf`](gateway/nginx.conf)) at http://localhost:8080. It's the only container published on the host. The services are reachable only on the Compose private network, by service name (e.g. `http://user-service:8000`). The databases are also published, but bound to `127.0.0.1` for host tooling. The reasoning is in [`docs/auth-plan.md`](docs/auth-plan.md).
- **Routing.** `/api/users/...` goes to user-service, `/api/suppliers/...` to supplier-service, `/api/orders/...` to order-service, and `/api/credits/...` to credit-service; every other path goes to the `frontend` container, which serves the built web app. So the app runs at http://localhost:8080 and calls the API on the same origin, with relative `/api/...` URLs. For the API routes, nginx strips the prefix, so each service defines its routes relative to its own root and doesn't repeat its name: `GET /api/suppliers/{id}` is `GET /{id}` in supplier-service.
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
| Nathan Tew | User Service, Integration |
| Aaron Rodrigues | Supplier Service, Credit Service |
| Yang Qifeng | Frontend |

---

## Repository Structure

This repository follows a **one-service-per-folder** structure: each
microservice (`user-service/`, `supplier-service/`, `order-service/`,
`credit-service/`) lives in its own top-level folder.

```text
.
â”œâ”€â”€ user-service/
â”œâ”€â”€ supplier-service/
â”œâ”€â”€ order-service/
â”œâ”€â”€ credit-service/
â”œâ”€â”€ <n2h-service>/
â””â”€â”€ README.md
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

**Decisions made by the team before AI assistance:** FastAPI with SQLAlchemy Core for the user service; a `users` table with an auto-increment integer id; a separate admin table (later replaced by an admin role on `users`, see below).

**Used for:**
- **Explaining** implementation order (tables â†’ Alembic â†’ FastAPI), Docker Compose networking and service-name DNS, environment variable handling (`pydantic-settings` precedence, root vs. service `.env`), Docker layer caching with uv, and how a Compose setup differs from a Google Cloud Run deployment.
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
- **Explaining** session-token revocation options (short access tokens with stored refresh tokens, a gateway check, a shared denylist), now in `docs/auth-plan.md`. The team chose to keep the token's `type` claim and rename its user value to `student`; the AI applied this across user-service, supplier-service and the frontend.
- **Planning and generating** the change from separate admin accounts to users with an `admin` role (`docs/admin-role-plan.md`). This was a team decision. Admins now sign in through the same `/auth/login`, and the token's `type` claim became `role`. A new migration adds `users.role` and drops `admins`. Registration and `create-initial-admin` accept `@u.nus.edu` emails only, and admins are kept out of errand pages in the frontend. The AI applied this across user-service, supplier-service and the frontend, and updated the tests and docs.
- **Identifying** a gap in the admin-only design: with unique `@u.nus.edu` emails, a promoted student couldn't keep a student account, so they'd lose the ability to post and accept errands. The team chose the AI's recommended fix: admin is extra permissions on top of a student account. The AI removed `require_student`, showed the errand pages to admins in the frontend, and updated `docs/admin-role-plan.md` and `docs/auth-plan.md`.
- **Generating** `PATCH /users/me` (username and password changes, with a row lock around the password check) and its tests, written before the code. The AI recommended keeping `200` for no-op updates so retries stay safe; the team agreed and added a server-side rule that a new password must differ from the current one.
- **Generating** the frontend's connection to user-service: relative `/api/...` URLs with a Vite dev proxy (the team asked for an explicit dev-only target), registration, login and profile editing, and readable validation errors. It also aligned the backend's username and password rules with the frontend's, at the team's request.
- **Generating** the frontend container (`frontend/Dockerfile`, `frontend/nginx.conf`) and its Compose service behind the gateway, and **explaining** why a built app needs a static file server and how the ports fit together.

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

### Credit Service and RabbitMQ

**Tool and mode:** Claude (claude.ai, model: Claude Opus 5.5), suggest, explain and debug (2026-10-17).

**Decisions made by the team before AI assistance:** FastAPI with SQLAlchemy and PostgreSQL, the credit service's own database in `credit-service/`, RabbitMQ as the broker, every balance change sent as an asynchronous message rather than an event, and a "pending" state on the wallet until credits are applied. Requirements F12–F14 and N5 from the backlog.

**Used for:**
- **Suggesting** the credit service setup: the `wallets`, `reservations` and `ledger_entries` tables and migration, the idempotent reserve/adjust/transfer/release/open-wallet operations, the message contract, the RabbitMQ worker, the read-only API, the audit, the `credit-demo` stand-in for the Order Service, the Dockerfile, and 59 tests.
- **Suggesting** the RabbitMQ setup (`rabbitmq/definitions.json`, `rabbitmq/provision.sh`): one login per service, topic permissions, quorum queues and dead-lettering. We tested the broker's behaviour before relying on it, and found that RabbitMQ 4 doesn't count `nack(requeue=True)` towards the delivery limit, so the worker never requeues.
- **Generating** the User Service's transactional outbox for `OpenWallet` (`outbox` table and migration, relay, `resync-wallets`) and its tests, and the Compose, gateway and `.env.example` entries.
- **Generating** the credit banner's connection to `GET /api/credits/wallets/me`, with the pending state.
- **Explaining** the design and answering the Part 2 and Part 4 review questions in [`docs/credit-service-plan.md`](docs/credit-service-plan.md), including the integration steps for the Order Service.

**Verification:** credit-service tests (59, 85% line coverage excluding the demo tool) and user-service tests (102, including the existing 95) pass against Postgres. The full stack was built and run with `docker compose up --build`, and the AI ran failure drills: credit worker stopped while an errand completes, RabbitMQ stopped during registration, the credit database stopped mid-command, a broker restart, invalid and unauthorised messages, three competing workers, and all containers recreated with a command still queued. The banner was checked in a browser at 1280px and 390px. <!-- TODO(author): describe your own review and testing -->

### Frontend Client (Yang Qifeng)

**Tools:** Claude Code (model: Claude Opus 5.5)

**Decisions made by the team before AI assistance:** React and Vite for the existing web client; its supplier UI, user forms, fields, and client-side validation rules; and using the nginx gateway as the application's public entry point.

**Used for:**

- **Wiring** the client to the User and Supplier Services through relative `/api/...` URLs, including a Vite development proxy, typed API clients, token-based session handling, registration, login, profile editing, supplier listing, supplier details, and supplier updates.
- **Reviewing and aligning** client request and response types, validation, loading states, permissions, pagination, and user-facing API errors with the service contracts.
- **Generating** the frontend Docker and nginx configuration and adding the frontend Compose service so the built single-page app is served behind the gateway.

**Verification:** `npm run build` and lint passed; nginx configuration was validated with `nginx -t`. <!-- TODO(author): describe your own review and testing -->

### Frontend UI Extensions

**Tool and mode:** OpenAI Codex (GPT-5), UI generation, refactoring, and debugging (2026-10-15â€“16).

**Prompts and key results:**

- â€œokay now abstract the section out as a component, put under components/credit-banner, then import into explore, my-tasks and my-requests conciselyâ€ â†’ A shared credit banner on all three pages; credit amounts are placeholders.
- â€œokay finally, lets extend the shared-toolbar abstraction, to allow for no tabs, and instead the replacement being a subheader text option, which explore will call and put "Available Tasks"â€ â†’ One configurable Toolbar serves Explore, My Tasks, My Requests, and Suppliers.
- â€œokay, now within supplier-details, lets also import the interactive-map abstraction but lets tweak it minimally, so that its read only (normal/fullscreen, still with teh read boundary)â€ â†’ Shared React-Leaflet map for request and supplier editing, plus read-only supplier details. It marks the rectangular served-area boundary and shades the outside red; fullscreen editing saves on explicit close.
- â€œ1) Building, floor, description is set by user, remove the dependence to supplier 2) Rename "your pickup location" as just Location 3) Remove the extra info, make Deliver By and Credits into two separate linesâ€ â†’ The create-request dialog has supplier search, user-defined delivery details, map location, delivery time (default: 30 minutes ahead), credits, and client-side validation. Submission remains UI-only until the Order Service is connected.

**Verification:** `npm run build` and lint passed; nginx configuration was validated with `nginx -t`. <!-- TODO(author): describe your own review and testing -->


### Order Service AI Autofill

**Tool and mode:** OpenAI Codex (GPT-6), planning, generation, debugging, and explanation (2026-10-17).

**Prompt (verbatim):** "okay good, execute concisely and codebase aligned now"

**Key response:** Added a database-free FastAPI order-service with authenticated `POST /autofill`, backend-only Groq structured extraction, active supplier matching, and gateway/Compose wiring. Connected the frontend AI Autofill view with a 20–500-character prompt, counter, blocking loading state, errors, and partial suggestions that replace existing values when non-null. Request creation remains a separate unimplemented operation. The preceding planning request specified these requirements.

**Files affected:** Each changed source and configuration file carries an AI Assistance Disclosure header. The generated `order-service/uv.lock` also identifies AI assistance.

**Files affected:** each carries an "AI Assistance Disclosure" header comment.

**Prompts and key exchanges:** see [`ai/usage-log.md`](ai/usage-log.md).
### Order Service (Nathan)

**Tool and mode:** Claude Code (model: Claude Opus 5.5), review, explain and generate (2026-10-18 to 2026-10-19).

**Decisions made by the team before or during AI assistance:**
- The Order Service integrates with the Credit Service through the asynchronous credit-transaction workflow.
- Only the requester cancels, and only while OPEN. Unfinished errands expire at their deadline; only the requester's confirmation gets a 5-minute grace period after it. The reserved credits are returned.
- Supplier details are not copied onto errands.
- Delivery locations move from supplier-service to order-service.
- Supplier-name search runs on the server.
- Errands whose supplier has been deactivated can't be accepted; the requester can still cancel them. Cancelling them automatically, by a sweeper or a supplier-service event, was rejected for this project's scope.
- Edits can't move an errand's deadline more than 24 hours past when it was posted, so reserved credits can't be held indefinitely.
- The work is built one reviewed task at a time.

**Used for:**
- **Reviewing** the other services against the D3 milestone and **planning** the Order Service in [`docs/order-service-plan.md`](docs/order-service-plan.md): schema, state machine, credit commands over RabbitMQ, API, and task order.
- **Generating** the Order Service infrastructure and skeleton (Task 1):
  - the `order-db`, `order-migrate` and `order-worker` Compose services and the exact-match `/api/orders` gateway route;
  - Alembic, `db.py`, `auth.py`, `errors.py`, `broker.py`, `/health`, and a placeholder worker;
  - autofill moved into `routes/autofill.py`;
  - Testcontainers-based tests.
- **Generating** the data layer (Tasks 2 and 3):
  - the `errands` and `outbox` tables with CHECK constraints, the errand states and credit statuses, and the outbox relay generalised from user-service;
  - delivery locations copied from supplier-service: personal locations private to their creator, predefined ones editable by admins, no edits while a courier is on the way, and a seed of the 100 predefined locations.
- **Generating** the calls to other services (Tasks 4 and 5):
  - one pooled client that forwards the user's token, for supplier details (batched through supplier-service's new `GET /lookup`), usernames and the advisory wallet check, each falling back to `null` when the service is down;
  - user-service's internal `GET /internal/usernames`, which the gateway blocks, so only services can call it.
- **Generating** errand creation, reading and listing (Task 6): create writes the errand, its delivery point and the `ReserveCredits` command in one short transaction, after the supplier and wallet checks; Explore, My Requests, My Tasks and an admin list search, sort and page. No database connection is held while another service is called.
- **Generating** the errand lifecycle (Task 7): accept, pick up, deliver, complete, cancel and edit, each one conditional `UPDATE` with its credit command written to the outbox in the same transaction, and refusals explained as 404, 403 or 409.
- **Generating** the Credit Service reply handling (Task 8): a reply is applied only while the errand's credits are PENDING, only if it reaches where the errand's state says the credits should end up, and only for the latest reward change, so duplicate and out-of-order replies never move credits backwards. A refused reserve cancels the errand.
- **Explaining** the code for the author's review: the delivery-location share lock, `Engine` versus `Connection` dependencies, the locked read in edit, and the request and response models. Explanations of the locks and transactions were added to the D3 document.

**Verification:** 229 order-service tests pass, including concurrent accepts, accept against cancel, complete sent twice and the deadline guards; the race tests passed on six repeated runs. Task 1 also passed `docker compose config`, `nginx -t` and the image build. <!-- TODO(author): describe your own review and testing -->
