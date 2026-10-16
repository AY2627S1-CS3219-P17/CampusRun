<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
Tool: OpenAI Codex (GPT-6), date: 2026-10-16
Scope: AI-written "Gateway, root paths and API docs" section and AI Use Summary bullets, including the frontend AI entry view disclosure; the rest was written by the team.
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
| Nathan Tew | User Service, Integration |
| Aaron Rodrigues | Supplier Service |
| Yang Qifeng | Frontend |

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

**Decisions made by the team before AI assistance:** FastAPI with SQLAlchemy Core for the user service; a `users` table with an auto-increment integer id; a separate admin table (later replaced by an admin role on `users`, see below).

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

### Frontend Client (Yang Qifeng)

**Tools:** Claude Code (model: Claude Opus 5.5)

**Decisions made by the team before AI assistance:** React and Vite for the existing web client; its supplier UI, user forms, fields, and client-side validation rules; and using the nginx gateway as the application's public entry point.

**Used for:**

- **Wiring** the client to the User and Supplier Services through relative `/api/...` URLs, including a Vite development proxy, typed API clients, token-based session handling, registration, login, profile editing, supplier listing, supplier details, and supplier updates.
- **Reviewing and aligning** client request and response types, validation, loading states, permissions, pagination, and user-facing API errors with the service contracts.
- **Generating** the frontend Docker and nginx configuration and adding the frontend Compose service so the built single-page app is served behind the gateway.

**Verification:** `npm run build` and lint passed; nginx configuration was validated with `nginx -t`. <!-- TODO(author): describe your own review and testing -->

### Frontend UI Extensions (Yang Qifeng)

**Tool and mode:** OpenAI Codex (GPT-5), UI generation, refactoring, and debugging (2026-10-15–16).

**Prompts and key results:**

- “okay now abstract the section out as a component, put under components/credit-banner, then import into explore, my-tasks and my-requests concisely” → A shared credit banner on all three pages; credit amounts are placeholders.
- “okay finally, lets extend the shared-toolbar abstraction, to allow for no tabs, and instead the replacement being a subheader text option, which explore will call and put "Available Tasks"” → One configurable Toolbar serves Explore, My Tasks, My Requests, and Suppliers.
- “okay, now within supplier-details, lets also import the interactive-map abstraction but lets tweak it minimally, so that its read only (normal/fullscreen, still with teh read boundary)” → Shared React-Leaflet map for request and supplier editing, plus read-only supplier details. It marks the rectangular served-area boundary and shades the outside red; fullscreen editing saves on explicit close.
- “1) Building, floor, description is set by user, remove the dependence to supplier 2) Rename "your pickup location" as just Location 3) Remove the extra info, make Deliver By and Credits into two separate lines” → The create-request dialog has supplier search, user-defined delivery details, map location, delivery time (default: 30 minutes ahead), credits, and client-side validation. Submission remains UI-only until the Order Service is connected.

**Verification:** `npm run build` and lint passed; nginx configuration was validated with `nginx -t`. <!-- TODO(author): describe your own review and testing -->

**Files affected:** each carries an "AI Assistance Disclosure" header comment.

**Prompts and key exchanges:** see [`ai/usage-log.md`](ai/usage-log.md).
- **Refactoring** the Explore task card into a shared component (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
   <article className="explore-task-card">
            <h2>Pick up printed notes</h2>
            <span className="explore-task-status">Open</span>
            <p className="explore-task-location">
              <MapPin size={16} aria-hidden="true" />
              <span>
                COM3 Print Shop&nbsp;&nbsp;&rarr;&nbsp;&nbsp;Central Library
              </span>
            </p>
            <p className="explore-task-due">
              <CalendarDays size={16} aria-hidden="true" />
              <span>Due 21 Apr, 5:00 PM</span>
            </p>
            <span className="explore-task-reward">
              <span>+10</span>
              <CircleDollarSign size={20} aria-hidden="true" />
            </span>
          </article>

  Lets abstract out this shadow card, with a type parameter (for now just put "open" and map it to the green color)
  ```

  Key response: extracted a shared TaskCard with content props, passed `type="open"` from Explore, and mapped that type to the existing green badge styling.

- **Extending** task card status variants and tab examples (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  okay now add a pending type -> map to orange

  &#x20;                          cancelled and expired types -> map to \<some negative shades>  &#x20;

  &#x20;                          completed tyoe -> map to \<some positive shade

  &#x20;                          accepted, picked up and delivered types -> map to \<some intermediate shades>

  then, under the my-tasks and my-requests

  - pending section: have a single pending type card
  - active section: have one of each (accepted, picked up and delivered) cards
  - completed section: have a single completed type card
  - inactive section: have one of each (canclled, expired) cards
  ```

  Key response: added orange pending, distinct intermediate active, positive completed, and negative inactive badge colors; both My Tasks and My Requests now display hardcoded sample cards for the selected tab.

- **Unifying** active and inactive task card colors (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  okay for inactive tab, lets just use one  of the two red shades for both expired and cancelled
  then for active tab, lets just use the delivered shade (but abit more contrast and a slight touch of purple) for all as well
  ```

  Key response: Accepted, Picked up, and Delivered share a stronger blue-violet badge; Cancelled and Expired share the existing cancelled red badge.

- **Recoloring** the shared active task badge (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  .task-card-status-accepted,
  .task-card-status-picked-up,
  .task-card-status-delivered {
    color: #3b5278;
    background: #e8edf8;
  }

  ah fuck never make it a lighter shade of green similar to the delievered shade previously
  ```

  Key response: Accepted, Picked up, and Delivered share a light mint-green badge, close to the earlier Delivered palette.

- **Distinguishing** active badges from Completed (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt: "hmm feel its still abit too similar to the completed green, can we add a small touch of some other shade (netural or non neutral) that retains the contrast with everything else, but makes it mor edistinct". Key response: shifted the shared active badge toward muted teal while retaining strong text contrast.

- **Separating** active badges from the credit blue (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt: "no too similar to the dollar blue, something else". Key response: changed the shared active badge to muted sage with a light neutral-green background.

- **Trying** the Shopping supplier purple for active task badges (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt: "hm actually lets try the purple for supplier type == Shopping". Key response: Accepted, Picked up, and Delivered now use the Shopping badge's purple text and background colors.

- **Adding** an optional negative credit sign to task cards (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  okay good, so now, lets add a new optional parameter to task-card abstraction
  is-negative or something concise, where it flips the sign to -
  then, the my_requests sample entries all has it
  ```

  Key response: added an optional `negative` prop to TaskCard and enabled it for every My Requests sample card, while the other cards retain positive amounts.

- **Extracting** shared pagination for supplier and task pages (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  Okay now maybe abstraction the pagination out, and give the supplier pagination to the explore/my-request/my-tasks pages

  note that similar to supplier, separate subtabs (eg: active, inactive etc.) have their own pagination
  ```

  Key response: moved the supplier pager into a shared Pagination component, added it to Explore, My Tasks, and My Requests, and stored separate page numbers for each task/request tab. Supplier keeps its service-side page size; placeholder task cards paginate two per page.

- **Cleaning frontend CSS** (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  okay finally, clean up the explore.css (and in general all .css files for unused or redundant styles)
  ```

  Key response: removed the stale direct-card selector in Explore, unused supplier sign-in and profile-description rules, and declarations overridden by later CSS; consolidated duplicate supplier and request-input rules while retaining responsive and dynamically generated styles.

- **Adding Open to active My Requests** (OpenAI Codex, GPT-6, 2026-10-16). Exact prompt:

  ```text
  okay now for my requests active tab only, it should also support open type (liek its our requests) right?
  if agree, add it in, then make the color purple still
  ```

  Key response: added an Open sample card only to the My Requests Active tab and styled that card's Open badge purple; Explore Open badges remain green.
