<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
Scope: AI-generated D3 gap check and implementation plan for the Order Service (schema, state machine, credit
       integration over RabbitMQ, API, worker, infrastructure, delivery-location move, frontend wiring, tests);
       revised the same day with the team's decisions.
Author review: <to be completed by author>
-->

# Order Service Plan

Last updated: 2026-10-18 (revised with the team's decisions)

> **How this plan is carried out:** one task at a time, inline in a session (superpowers:executing-plans).
> **After every task, stop for a manual review.** Walk through the diff, answer questions and make any changes
> before the next task starts. Write the detailed code for a task only when that task begins, since earlier
> reviews may change it.

**Goal:** Build the Order Service that runs the errand lifecycle (Milestone D3 Part 1). It integrates with the User,
Supplier and Credit Services, and its credit operations run asynchronously over RabbitMQ (Part 3).

**Architecture:** A FastAPI HTTP API plus an `order-worker` process, both built from one image and sharing one
Postgres database.
- Every state change is a single conditional `UPDATE`. A change that moves credits writes its credit command to an
  `outbox` table in the same transaction.
- The worker publishes the outbox, consumes the credit service's `ReservationResult` replies, and runs the
  time-based transitions (expiry, reconciliation).

**Tech stack:** Python 3.14.7, FastAPI, SQLAlchemy Core (async, asyncpg), Alembic, aio-pika, Postgres 18,
RabbitMQ 4.3, uv, pytest. These are the same versions as credit-service.

---

## 1. Decisions

| # | Decision | Effect on the design |
|---|---|---|
| D1 | Only the requester can cancel, and only while OPEN | One cancel rule: `state='OPEN' AND requester_id=:me`. No courier or admin cancel. |
| D2 | `deliver_by` is the deadline for everything except the requester's confirmation, which has a grace period of `EXPIRY_GRACE_MINUTES` (5). Errands not yet delivered expire at `deliver_by`; DELIVERED ones at `deliver_by + grace` | OPEN, ACCEPTED, PICKED_UP and DELIVERED all expire. The courier isn't paid; the requester gets the reserved credits back (`ReleaseCredits{reason:'EXPIRED'}`). |
| D3 | A delivered but unconfirmed errand waits for confirmation or for expiry | No auto-complete. `complete` works until `deliver_by + grace`; nothing else does. |
| D4 | No `pending` tab | Pending = an errand whose `credit_status` is PENDING. It appears in the normal tabs with a "credits processing" badge. |
| D5 | No accept cutoff before the deadline | Accept only requires `deliver_by > now()`. |
| D6 | Don't copy supplier details onto errands | Store `supplier_id` only. Responses fetch the supplier live, so supplier edits change existing errands (accepted trade-off). |
| D7 | `delivery_locations` moves from supplier-service to order-service | Copy first (Task 3). Remove it from supplier-service only after the switch is confirmed (Task 10). Errands then reference it with a real foreign key. |
| D8 | Usernames are returned inside errand responses | The frontend never looks up users. Order-service calls an internal user-service endpoint (Task 5). |
| D9 | Build step by step with a review after each task | See the note at the top. |
| D10 | The requester can edit an errand only while it's OPEN | It can't be edited once a courier accepts. The same applies to a delivery location: nobody can edit it while an errand using it is ACCEPTED, PICKED_UP or DELIVERED (a courier is on the way). Finished errands don't block edits, or a predefined location could never change again. |
| D11 | Suppliers only need to be active when an errand is created | Whether the supplier is open isn't checked. |
| D12 | Searching by supplier name happens on the server | Search, sort, tab and page changes each send a request, debounced as on the Suppliers page. Order-service asks supplier-service for the ids of matching suppliers, then filters errands by `supplier_id` (section 7). |
| D13 | A deactivated supplier's errands can't be accepted | Accept checks the supplier is still active (409 otherwise); the web client shows "Supplier unavailable" and lets the requester cancel while OPEN. Errands with a courier carry on or expire. Rejected: the sweeper cancelling them (needs service credentials), and a SupplierDeactivated event or a synchronous callback from supplier-service (more work; neither closes the creation race alone). |

**No separate "reserving" state for OPEN-and-pending.** `credit_status` already covers it, and it also covers the
other pending cases (COMPLETED with the transfer in flight, CANCELLED/EXPIRED with the release in flight). One
column handles all three. A new state would only cover the first, and would change the glossary's lifecycle. Explore
lists only errands whose credits are HELD, so to couriers an OPEN-and-pending errand doesn't exist yet.

**Consequence of D2 and D3 to be ready to explain at D3:** if the deadline is 5:00, the courier must deliver by
5:00, and the requester can still confirm until 5:05. An errand not delivered by 5:00 expires then; one delivered but
not confirmed by 5:05 expires then, and the courier isn't paid. The grace period moves the confirmation cut-off but
doesn't remove it.

## 2. D3 readiness check (everything except the Order Service)

Checked by reading the code on `main` at `fb2cdb1`. The test suites weren't run, and the full stack wasn't started.

| Area | Status | Gap |
|---|---|---|
| User Service | Done | No way to look up another user's username (Task 5) |
| Supplier Service | Done | Will lose `delivery_locations` (Task 10) |
| Credit Service | Done | — |
| RabbitMQ | Done | `definitions.json` already has the `order-service` login, permissions and reply queue; no changes needed |
| Gateway | Done | Exact-match `location = /api/orders` added 2026-10-18 (not yet run: Docker was off) |
| Containerisation | Order service missing | No database, migrate step or worker in Compose: Task 1 |
| Frontend | UI only for errands | Explore, My Requests and My Tasks show `SAMPLE_TASK_CARDS`; create submit is a stub; edit and CTA buttons have no handlers: Task 12 |
| Docs | Missing | `docs/credit-service-plan.md` is cited but was never committed. Ask Aaron for it. This plan doesn't depend on it, so reconcile it when it arrives. |
| Local env | Stale | The root `.env` lacks the RabbitMQ and credit variables (see the README's getting-started) |

## 3. Structure

Use credit-service as the skeleton, take `outbox.py` from user-service, and keep the endpoints split into `routes/`.

- **Credit-service** already has a separate worker process (credit-service API plus `credit-worker`, from one
  image), a reply-consuming RabbitMQ consumer, `CurrentUser.id: int`, a `routes/` package and the
  `{"detail", "errors"}` 422 format the create form needs.
- **User-service** is the only service with an outbox.
- User-service's single `main.py` doesn't scale well to about 15 endpoints plus a worker.

```
order-service/src/order_service/
  config.py        settings: DATABASE_URL, RABBITMQ_URL, USER/SUPPLIER/CREDIT service URLs, SWEEP_SECONDS,
                   RECONCILE_AFTER_MINUTES, served-area bounds
  db.py            copy of credit-service/db.py
  auth.py          copy of credit-service/auth.py (CurrentUser.id: int, AnyUser, AdminUser)
  errors.py        copy of credit-service/errors.py
  tables.py        delivery_locations, errands, outbox
  schemas.py       request/response models (camelCase) + the autofill models
  states.py        State and CreditStatus enums, and target_credit_status(state)
  transitions.py   one function per transition: conditional UPDATE (+ outbox insert)
  outbox.py        enqueue() + relay, generalised from user-service/outbox.py
  credit.py        ReservationResult mirror + apply_reply()
  clients.py       httpx: suppliers by id, usernames by id, wallet pre-check
  sweeper.py       expire_due(), reconcile()
  broker.py        copy of credit-service/broker.py
  worker.py        order-worker: relay + reply consumer + sweeper loops
  seed.py          seeds predefined delivery locations (copied from supplier-service)
  main.py          app, lifespan, /health, router order
  routes/
    autofill.py            POST /autofill (moved unchanged)
    delivery_locations.py  /delivery-locations CRUD
    mine.py                GET /me/requests, GET /me/tasks
    admin.py               GET /admin/errands, GET /admin/stuck
    errands.py             POST /, GET /, GET /{id}, PATCH /{id}
    actions.py             POST /{id}/accept|pickup|deliver|complete|cancel
```

Include `errands` and `actions` last. Otherwise `/{errand_id}` catches `/me`, `/admin` and `/delivery-locations`
first and returns 422 (supplier-service has the same note in its `main.py`).

## 4. Schema

```
delivery_locations                       (copied from supplier-service, then extended)
  id               integer identity PK
  name             varchar(100) not null       building name, e.g. "COM3"
  floor            varchar(10) null            NEW: the form collects it
  description      varchar(300) null           now optional: the form's description is optional
  latitude         double not null             inside the served area
  longitude        double not null
  active           boolean not null default true
  predefined       boolean not null default false   the shared campus list (seeded or admin-added)
  created_by       integer null                the user who added it; NULL only for seeded rows
  updated_by       integer null
  created_at, updated_at
  unique lower(name) only WHERE predefined  (users' own locations may share names)
  CHECK predefined OR created_by IS NOT NULL

errands
  id                    integer identity PK       = errandId in every credit command
  requester_id          integer not null          user-service id (JWT sub)
  courier_id            integer null
  state                 varchar(16) not null      OPEN|ACCEPTED|PICKED_UP|DELIVERED|COMPLETED|CANCELLED|EXPIRED
  credit_status         varchar(16) not null      PENDING|HELD|REJECTED|TRANSFERRED|RELEASED
  credit_rejection      varchar(32) null          last rejection from the credit service, shown to the requester
  title                 varchar(100) not null
  reward                integer not null          1..100
  reward_revision       integer not null default 0
  supplier_id           integer not null          supplier-service id (no copied details: D6)
  delivery_location_id  integer not null FK delivery_locations.id
  deliver_by            timestamptz not null      15 min .. 24 h after creation
  cancel_reason         varchar(32) null          REQUESTER | INSUFFICIENT_CREDITS | NO_WALLET
  created_at, updated_at, accepted_at, picked_up_at, delivered_at, completed_at, cancelled_at, expired_at

  CHECKs: state IN (...); credit_status IN (...); reward BETWEEN 1 AND 100; courier_id <> requester_id;
          state IN ('OPEN','CANCELLED','EXPIRED') OR courier_id IS NOT NULL
  Indexes: (state, credit_status, deliver_by); (requester_id, state); (courier_id, state);
           (credit_status, updated_at)

outbox      same columns as user-service's outbox table
```

**Delivery point on create:** the request either names an existing active location (`deliveryLocationId`, a
predefined one or one of the requester's own), or gives `building, floor?, description?, latitude, longitude`. In
the second case a new `delivery_locations` row (`created_by = requester`) is inserted in the same transaction as the
errand. Only the location's creator (or an admin, for predefined ones) can edit it, and edits show on every errand
that uses it, consistent with D6.

**Referenced data that changes or disappears:**
- Suppliers are never deleted (they're deactivated), so an errand shows the supplier's current details.
- If supplier-service can't find or reach a supplier, the response has `supplier: null` and the UI shows a
  placeholder.
- The same applies to usernames.

## 5. State machine

Every transition is one `UPDATE errands SET … WHERE id = :id AND <guard> RETURNING *`. The row lock serialises
racing requests, so the loser matches 0 rows. On 0 rows, read the errand again and answer:
- **404** if the caller may not see it;
- **403** if it's the wrong party;
- **409** if it's in the wrong state or past the deadline, e.g. `{"detail": "This errand was already accepted."}`.

Two time guards, written below as `due` and `live`:
- `due` = `now() < deliver_by`: required to **accept**, **pick up**, **deliver**, **cancel** and **edit**.
- `live` = `now() < deliver_by + grace`: required to **complete** only, so the requester can confirm an errand that
  was delivered just before the deadline.

The sweeper expires errands not yet delivered at `deliver_by`, and DELIVERED ones at `deliver_by + grace`. Every
action checks its own time guard, so a sweeper that runs late can't let anything progress.

| From → To | By | Guard (in the WHERE) | Credit command | credit_status |
|---|---|---|---|---|
| — → OPEN | requester `POST /` | supplier exists and active; location in area; deadline in range | ReserveCredits | PENDING |
| OPEN → OPEN (edit) | requester `PATCH /{id}` | `state='OPEN' AND requester_id=:me AND credit_status='HELD'` + due | AdjustReservation if `credits` changed (revision+1) | PENDING if adjusted |
| OPEN → ACCEPTED | courier `/accept` | `state='OPEN' AND credit_status='HELD' AND requester_id<>:me` + due | — | HELD |
| ACCEPTED → PICKED_UP | courier `/pickup` | `state='ACCEPTED' AND courier_id=:me` + due | — | HELD |
| PICKED_UP → DELIVERED | courier `/deliver` | `state='PICKED_UP' AND courier_id=:me` + due | — | HELD |
| DELIVERED → COMPLETED | requester `/complete` | `state='DELIVERED' AND requester_id=:me` + live | TransferCredits | PENDING |
| OPEN → CANCELLED | requester `/cancel` | `state='OPEN' AND requester_id=:me` (any credit_status) + due | ReleaseCredits(CANCELLED) | PENDING |
| OPEN → CANCELLED | reply handler | reserve reply REJECTED | — | REJECTED |
| OPEN/ACCEPTED/PICKED_UP → EXPIRED; DELIVERED → EXPIRED | sweeper | `deliver_by <= now()`; for DELIVERED, `deliver_by + grace <= now()` | ReleaseCredits(EXPIRED) | PENDING |

An edit while the reserve reply is still outstanding (credit PENDING) gets 409 "Your credits are still being
reserved. Try again in a moment."

**D3 corner cases:**
- **Two couriers accept at once:** the second waits for the row lock, then re-checks `state='OPEN'`, matches 0 rows
  and gets 409.
- **Accept at the same moment as cancel or expiry:** whichever commits first wins. Accept checks the deadline itself.
- **Delivery near the deadline:** the courier must deliver by the deadline; the requester can still confirm during the
  grace period. The sweeper and a confirmation race only at `deliver_by + grace`, where the row lock decides.
- **Complete submitted twice:** the second gets 409 "already completed". Even a duplicate TransferCredits pays only
  once.
- **Cancel before the reserve reply arrives:** ReleaseCredits follows ReserveCredits in outbox order. The credit
  service's release-before-reserve placeholder covers any reordering.
- **Same student as requester and courier:** allowed on different errands. The accept guard and a CHECK stop
  anyone accepting their own errand.

## 6. Credit integration over RabbitMQ

- **Message-based** (commands to one receiver), matching `credit_service/commands.py`.
- **Sending:** the relay in `order-worker` publishes to `credit.commands`:
  - routing keys `reservation.reserve|adjust|transfer|release`;
  - `user_id="order-service"`, `type`, `message_id` = the outbox uuid;
  - persistent delivery and `mandatory=True`.

  A message counts as sent only on `Basic.Ack`.
- **Receiving** `order-service.credit-replies`:
  - Reject anything not from `user_id="credit-service"` with `type="ReservationResult"`.
  - Apply the reply in one transaction (errand locked `FOR UPDATE`), then ack.
  - Never `nack(requeue=True)`.
- **Target rule.** The state alone decides where credit should end up:

| State | Target credit_status | Command that reaches it |
|---|---|---|
| OPEN, ACCEPTED, PICKED_UP, DELIVERED | HELD | ReserveCredits / AdjustReservation |
| COMPLETED | TRANSFERRED | TransferCredits |
| CANCELLED, EXPIRED | RELEASED, or REJECTED if nothing was held | ReleaseCredits |

- **`apply_reply`:**
  - If the reply's status equals the target (and, for an adjust, `revision == reward_revision`), set
    `credit_status` and `credit_rejection`. For an adjust, set `reward = reply.amount`; on `INSUFFICIENT_CREDITS`
    that reverts the edit.
  - A reserve `REJECTED` on an OPEN errand cancels it (`cancel_reason = reply.reason`, credit REJECTED). This is the
    only reply that changes state.
  - Anything else is logged and acked unchanged. Examples:
    - a reply with status `HELD` on an already-cancelled errand;
    - `NO_COURIER_WALLET`;
    - `status: null`;
    - an unknown `errandId`;
    - anything that would move credit backwards.
- **Reconciler:** errands whose `credit_status` is off target for longer than `RECONCILE_AFTER_MINUTES` get the
  target's command resent. This is safe because every command is idempotent. `GET /admin/stuck` lists them.
- **Pre-check (advisory):** `POST /` reads `GET {CREDIT_API_URL}/wallets/me` with the caller's token for an early
  422 on `credits`. If the call fails, skip the pre-check; the worker's reserve is the authoritative check.
- **D3 failure answers:**
  - *Credits reserved but order creation failed:* can't happen. The command exists only if the errand committed.
  - *Saved but not published:* it waits in the outbox.
  - *Completed while transfers are down:* COMPLETED + PENDING ("credits processing"), paid when the credit worker is
    back.

**The background sweeper isn't a cronjob.** It's an asyncio loop inside `order-worker`: every `SWEEP_SECONDS`
(default 30) it runs `expire_due()` then `reconcile()`, the same polling pattern as user-service's outbox relay.
- Each step is one statement using `FOR UPDATE SKIP LOCKED`, so several worker copies never process the same errand
  twice.
- Correctness doesn't depend on its timing, because every transition checks the deadline itself; the sweeper only
  decides how soon the credits come back.
- A cron container or Cloud Scheduler could replace the loop later without code changes, by calling the same two
  functions.

## 7. API

Paths are relative to the service; the gateway adds `/api/orders`. JSON is camelCase. Lists use the supplier `Page`
shape. Errand responses embed:
- `supplier {id, name, building, floor, latitude, longitude} | null`, fetched for the page's distinct supplier ids
  in one batched `GET /lookup` call to supplier-service;
- `deliveryLocation {...}`;
- `requesterName` and `courierName` (null if user-service can't be reached);
- `creditStatus`.

They never include an email address.

| Method and path | Who | Notes |
|---|---|---|
| `POST /` | signed in | 201 + `Location: {ROOT_PATH}/{id}` |
| `GET /` | signed in | Explore: OPEN, credit HELD, before the deadline, not mine. `q` searches title, delivery location name and supplier name (see below). `sort` = the frontend's `most-recent`, `least-recent`, `most-credits`, `least-credits`. page/pageSize |
| `GET /{id}` | requester, courier, admin; anyone while it's in Explore | 404 otherwise |
| `PATCH /{id}` | requester while OPEN and HELD | title, supplier, delivery point, deadline, credits |
| `POST /{id}/accept`, `/pickup`, `/deliver`, `/complete`, `/cancel` | section 5 | returns the updated errand |
| `GET /me/requests?tab=`, `GET /me/tasks?tab=` | signed in | `active` = OPEN/ACCEPTED/PICKED_UP/DELIVERED, `completed` = COMPLETED, `inactive` = CANCELLED/EXPIRED |
| `GET /admin/errands?requesterId=&courierId=&state=` | admin | read-only |
| `GET /admin/stuck` | admin | errands whose credits are off target |
| `GET/POST/PATCH /delivery-locations[/{id}]` | list: signed in (predefined + own; `?predefined=true/false` narrows it). Create: signed in; `"predefined": true` in the body is admin-only. Edit: creator for their own, admin for predefined | copied from supplier-service, with these permission changes |
| `POST /autofill` | signed in | unchanged |

**Searching by supplier name (`q` on `GET /`, `/me/requests` and `/me/tasks`).** Errands store only `supplier_id`
(D6), so a search takes two steps:
1. Order-service calls supplier-service `GET /?q=<q>` twice at the same time, with `active=true` and
   `active=false`, so errands whose supplier was later deactivated still match. It follows pages the way autofill's
   `resolve_supplier` does, and collects the matching supplier ids. Supplier-service already searches name,
   building and location description with a trigram index, and there are only about 60 suppliers.
2. One SQL query with
   `title ILIKE :p OR delivery_locations.name ILIKE :p OR errands.supplier_id = ANY(:supplier_ids)`, so the total
   and the pages stay correct.

This costs one extra internal HTTP round trip per search, and only when `q` is non-empty. It keeps supplier names
live, consistent with D6. If supplier-service is down, the search runs on title and delivery location only. The
response then carries `"supplierSearch": false`, so the UI can say "supplier names couldn't be searched".

Rejected alternatives:
- Copying supplier names onto errands contradicts D6.
- Filtering in the browser only sees the loaded page.

## 8. Tasks

Stop for review after each task. Every task ends with passing tests (testcontainers Postgres, as in
`user-service/tests/conftest.py`; RabbitMQ faked, as in the credit-service worker tests).

### Task 1: Infrastructure and skeleton
- **Compose:**
  - `order-db` (postgres:18, `127.0.0.1:5436`, healthcheck, volume `order-db-data`);
  - `order-migrate` (`alembic upgrade head`, then seed);
  - `order-service` (+ `DATABASE_URL`, `USER_SERVICE_URL`, `CREDIT_API_URL`; depends on `order-migrate`);
  - `order-worker` (`command: ["order-worker"]`, `RABBITMQ_URL=amqp://order-service:…`, `restart: unless-stopped`,
    depends on `order-migrate` and healthy `rabbitmq`).
  - The API doesn't wait for RabbitMQ.
- **Env:** `ORDER_DB_USER/PASSWORD/NAME` in the root `.env.example` and in `order-service/.env.example`.
- **Code:** `pyproject.toml` (alembic, asyncpg, sqlalchemy[asyncio], aio-pika; dev: pytest-cov, testcontainers;
  script `order-worker`), `alembic.ini`, `migrations/`, `config.py`, `db.py`, `auth.py`, `errors.py`, `main.py`
  (`/health`), autofill moved to `routes/autofill.py`, a placeholder `worker.py` that connects and idles,
  `mise.toml`, `AGENTS.md`, `tests/conftest.py`.
- **Tests:** `/health`; existing autofill behaviour unchanged.
- **Check:** `docker compose config --quiet`; `docker compose up --build` starts every container.
- **Note:** `credit-demo` logs in as `order-service` and reads the same reply queue, so it takes replies meant for
  `order-worker`. Document "stop order-worker before running credit-demo" in the README.

### Task 2: Errand tables, states and outbox
- **Files:** `tables.py` (errands, outbox), migration, `states.py`, `outbox.py`, tests.
- **Produces:**
  - `State`, `CreditStatus`, `CancelReason`, `UNFINISHED`/`FINISHED`/`IN_PROGRESS`,
    `target_credit_status(state) -> frozenset[CreditStatus]`;
  - `enqueue(conn, command: str, payload: dict) -> None`. The routing key comes from `outbox.ROUTING_KEYS`, so a
    command can't be sent with the wrong key; an unknown command raises `ValueError`;
  - `RabbitPublisher(connection)`, which publishes on the worker's existing RabbitMQ connection;
  - `publish_pending(engine, publisher, batch_size=100) -> tuple[int, bool]`;
  - `OutboxRelay`.
- `errands.delivery_location_id` is `NOT NULL` with no foreign key yet. Task 3 adds the key along with the
  `delivery_locations` table.
- **Tests:** `test_migrations_match_tables`; the CHECK constraints (own courier, reward range); port user-service's
  `test_outbox.py` (order kept on failure, two relays never send the same row, a Return counts as failure).
- Credit-demo reservations used made-up errand ids (e.g. 41). Before the first integrated run, remove the
  `credit-db-data` volume, or start the errands identity at 1,000,000. Otherwise the credit service dead-letters a
  real ReserveCredits whose id matches an old demo reservation for a different requester.

### Task 3: Copy delivery_locations into order-service
- **Files:** `tables.py`, migration, `seed.py` + `seed/delivery-locations.csv` (copied), `schemas.py`,
  `routes/delivery_locations.py` (copied, then permissions changed as in section 7), `tests/test_delivery_locations.py`
  (ported from supplier-service).
- Supplier-service is not touched in this task.
- **Tests:** seeded rows have `created_by NULL`; a student creates their own location, sees it in the list, and
  another student can't see or edit it; editing a location used by an ACCEPTED errand → 409 (D10); an admin edits a predefined one; out-of-area lat/lng → 422; duplicate
  predefined name → 409, duplicate personal names allowed.

### Task 4: Service clients
- **Files:** `clients.py`, `schemas.SupplierSummary`, the lifespan in `main.py`, `tests/test_clients.py` (fake HTTP
  transport, no services needed).
- **Produces:** `ServiceClients`, one pooled `httpx.AsyncClient` created with the app, injected with the `Clients`
  dependency. Every call forwards the signed-in user's token.
  - `get_suppliers(ids, token) -> dict[int, SupplierSummary] | None`: supplier-service's new `GET /lookup?ids=1&ids=2`
    (up to 100 ids per request, added in this task). Unknown ids are left out, deactivated ones are kept; `None` if
    supplier-service is down.
  - `require_active_supplier(id, token) -> SupplierSummary`: raises `FieldError("supplierId", …)` (422) if the
    supplier is unknown or inactive, and 503 if supplier-service is down.
  - `search_supplier_ids(q, token) -> set[int] | None`: active and deactivated listings, every page; `None` if down.
  - `get_usernames(ids, token) -> dict[int, str] | None`: `GET /internal/usernames?ids=1&ids=2` in batches of 100;
    `None` if down.
  - `get_wallet(token) -> WalletBalance(status, available) | None`. This replaces the planned
    `available_credits`, so Task 6 can tell a PENDING wallet apart from a low balance.
- `USER_SERVICE_URL` and `CREDIT_API_URL` are set in Compose and `order-service/.env.example`.

### Task 5: Internal username lookup in user-service
- **Files:** user-service `main.py` (or a new `routes/internal.py`), schemas, tests; `gateway/nginx.conf`.
- `GET /internal/usernames?ids=1&ids=2` (at most 100 ids, a valid token required) → `[{id, username}]`. It returns
  usernames only, never emails.
- Gateway: `location /api/users/internal/ { return 404; }`, so only services on the private network can call it.
- **Tests:** returns the requested users only; more than 100 ids → 422; no token → 401; email never in the body.
- **Also align user-service `auth.py` with the other services:**
  - separate "Your session has expired. Sign in again." from "Your session is not valid. Sign in again.", and give
    a full sentence for a wrong role;
  - reject a token whose `role` isn't `student` or `admin`, or whose `sub` isn't a number;
  - keep `OAuth2PasswordBearer`: user-service issues tokens, so its `/docs` can log in with a password;
  - keep user-service's names (`Account`, `CurrentUser`, `CurrentAdmin`). The team decided against renaming them.

### Task 6: Create, read and list errands
- **Files:** `schemas.py`, `errand_views.py` (shared queries and responses), `routes/errands.py`, `routes/mine.py`,
  `routes/admin.py` (`/admin/errands`), `tests/fakes.py` (in-memory supplier, user and credit services), tests.
- Insert the errand (and a new location if needed) and `enqueue("ReserveCredits", …)` in one transaction.
- **As built:**
  - The API calls the reward `credits`, as the frontend does. The custom delivery fields are flat (`building`,
    `floor`, `description`, `latitude`, `longitude`), so 422 keys match the form's fields.
  - A `deliverBy` without a time zone is campus time (`TIMEZONE`, Asia/Singapore).
  - Responses add `expiresAt` (`deliverBy` + `EXPIRY_GRACE_MINUTES`).
  - Each page makes one `/lookup` call for suppliers and one `/internal/usernames` call for names.
  - No database connection is held while other services are called. Create checks the supplier and wallet first,
    then writes in one short transaction. Lists search suppliers before the query and add names and suppliers
    after it. A test checks the pool is empty during every service call.
- **Tests:**
  - 201 + Location with ROOT_PATH, and an outbox row with the right body;
  - custom delivery fields create a location owned by the requester; someone else's `deliveryLocationId` → 422;
  - unknown or inactive supplier → 422 on `supplierId`; supplier-service down → 503 and nothing written;
  - deadline under 15 min or over 24 h → 422; credits 0 or 101 → 422; pre-check shortfall → 422 on `credits`;
  - Explore hides credit-PENDING, past-deadline and own errands; each sort;
  - `q` matches by title, by delivery location name, and by supplier name (including a deactivated supplier);
    supplier-service down → title and location matches only, with `supplierSearch: false`; total and pages correct
    with `q`;
  - a stranger gets 404 on an ACCEPTED errand;
  - `/me/requests` and `/me/tasks` tabs;
  - names and supplier embedded; `supplier: null` when supplier-service is down.

### Task 7: Transitions
- **Files:** `transitions.py`, `routes/actions.py`, `PATCH` in `routes/errands.py`, tests.
- **Produces:** `accept`, `pick_up`, `deliver`, `complete`, `cancel`, `edit(conn, errand_id, user, changes)`. Each
  returns the row, or raises 404/403/409 after a 0-row update.
- **Supplier check on accept (D13):** before its transaction, accept calls supplier-service for the errand's
  supplier. A deactivated or missing supplier gets 409 "This supplier is no longer available." If supplier-service
  can't be reached, the accept goes ahead and the failure is logged: deactivation is rare, and refusing every accept
  during an outage costs more.
- **Tests:**
  - every edge in section 5, and every other edge → 409;
  - courier or admin cancel → 403;
  - cancel ACCEPTED → 409;
  - own errand accept → 403;
  - 10 accepts gathered → exactly one 200;
  - accept vs cancel gathered → one winner, and the outbox matches it;
  - complete twice → 200 then 409, with one TransferCredits;
  - every action except complete after `deliver_by` → 409; complete inside the grace period → 200, after it → 409
    (sweeper not run);
  - edit while ACCEPTED → 409; edit while credit PENDING → 409;
  - reward edits enqueue AdjustReservation with revisions 1 then 2;
  - accept refused while an adjust is pending;
  - accept refused (409) when the supplier is deactivated; allowed when supplier-service is down;
  - accept takes a share lock on its delivery location (`SELECT … FOR SHARE`), so it can't interleave with a location edit's in-use check (Task 3 takes `FOR UPDATE`).
- **As built:**
  - `transitions.py` holds each transition. `explain()` turns a 0-row update into 404, 403 or 409 with a specific
    message, e.g. "This errand isn't ready to deliver yet."
  - A courier who loses an accept race gets 409 "This errand has already been accepted.", not 404, even though the
    errand is no longer visible to them. This reveals only an errand's state, never its details.
  - Accept checks the supplier only when the accept could succeed.
  - Edits can't move `deliverBy` past 24 hours after the errand was created, so repeated edits can't keep credits
    held past the credit audit's 48-hour mark.
  - Raising the reward runs the advisory wallet check on the difference.

### Task 8: Reply handling
- **Files:** `credit.py`, tests.
- **Tests:**
  - each target reached by its reply;
  - a duplicate reply → no change;
  - TRANSFERRED then a late `HELD` reply → stays TRANSFERRED;
  - reserve REJECTED on OPEN → CANCELLED with its reason and gone from Explore;
  - cancel before the `HELD` reply → it is ignored, then RELEASED applied;
  - REJECTED after cancel → credit REJECTED, state unchanged;
  - adjust INSUFFICIENT_CREDITS → reward reverted;
  - `status: null` and unknown errandId → acked, no change.
- **As built:**
  - A reply is applied only while the errand's `credit_status` is PENDING. Every command sets PENDING when it's sent,
    so a duplicate, or a reply after the credits have settled, changes nothing. This also stops a release's reply
    (which has no `rejection`) from clearing the `credit_rejection` a refused reserve set.
  - For an errand that isn't finished, the reply's `revision` must equal `reward_revision`, including the reserve's
    reply (both start at 0).
  - A refused reserve cancels only an OPEN errand, and only for INSUFFICIENT_CREDITS or NO_WALLET. `reward` is set
    from the reply only for an unfinished errand, so the amount-0 placeholder of a release that overtook its reserve
    never touches it.
  - A transfer whose `courierId` differs from the errand's is ignored. NO_COURIER_WALLET (status HELD) leaves the
    errand PENDING for the reconciler.
  - `apply_reply` returns `applied`, `cancelled` or `ignored` and never raises for a well-formed reply. Checking the
    sender and acknowledging are the worker's job (Task 9).

### Task 9: Worker and sweeper
- **Files:** `broker.py`, `sweeper.py`, `worker.py`, `routes/admin.py` (`/admin/stuck`), tests.
- `order-worker` runs the relay, the reply consumer (prefetch 10) and the sweeper loop. It handles SIGTERM like
  `credit-worker`, and logs every transition and message with errand id, type and message_id (Part 3.4).
- **Tests:**
  - expire_due expires OPEN, ACCEPTED and PICKED_UP past `deliver_by`, and DELIVERED past `deliver_by + grace`, with
    ReleaseCredits(EXPIRED); a DELIVERED errand inside the grace period is untouched; COMPLETED is untouched;
  - two sweepers gathered → each errand expired once;
  - reconcile resends after the threshold and not before;
  - a fake reply from the wrong user_id is rejected; a valid one is applied then acked; a DB error leaves it unacked.
- **Check:** the demo script in Task 11 runs end to end through the API (curl or Postman).
- **As built:**
  - `sweeper.py`: `expire_due()` and `reconcile()`. Each batch is one `UPDATE` whose rows a CTE picks with `FOR UPDATE
    SKIP LOCKED`, re-checking the condition in the `UPDATE`. An errand expires once its next action is no longer
    allowed: not yet delivered, once `due()` is false (past `deliver_by`); DELIVERED, once `live()` is false (past the
    grace period). It reuses the transitions' own checks, so expiry follows any change to the deadline rule.
  - `reconcile()` resends the command for the errand's state: ReserveCredits (revision 0) or AdjustReservation for
    an unfinished errand, TransferCredits, or ReleaseCredits with CANCELLED or EXPIRED. It skips errands whose command
    is still unpublished in the outbox, and sets `updated_at` so the wait restarts. The sweep expires first, so a
    just-expired errand isn't sent a stale ReserveCredits.
  - `GET /admin/stuck` lists errands PENDING for longer than `RECONCILE_AFTER_MINUTES`, including those still waiting
    in the outbox (the broker is down), which the reconciler leaves alone.
  - The reply queue has no dead-letter queue (`definitions.json` is unchanged), so a reply that fails the sender,
    type or body check, or fails 3 times unexpectedly, is rejected and dropped. The reconciler resends the command
    later, and the Credit Service replies again. A database outage holds the reply unacknowledged and retries.
  - Logs: every transition (errand, action, user); each reply with its `message_id` and `correlation_id` (the
    command's `message_id`), status and outcome; each expiry and resend. The relay already logs each publish.
  - `expiresAt` in responses is `deliverBy`, plus the grace period once the errand has been delivered (`delivered_at`
    set), so it stays consistent with `completedAt` and `expiredAt` after the errand ends.
  - Settings: `SWEEP_SECONDS` (30), `RECONCILE_AFTER_MINUTES` (5), `WORKER_PREFETCH` (10).

### Task 10: Remove delivery_locations from supplier-service (only after Task 9 is confirmed working)
- **Files:** supplier-service `tables.py` + a new migration that drops the table, `routes/delivery_locations.py`
  removed, the router include removed from `main.py`, the seed code and CSV removed, tests removed/updated,
  README/AGENTS.md updated.
- **Check:** the supplier-service tests pass; nothing references `/api/suppliers/delivery-locations` (it's unused
  by the frontend today).

### Task 11: Docs and D3 answers
- Update the D3 doc: Part 1 schema (sections 4 and 5 here), the state table, the failure answers, and a Part 3
  sample payload with an explanation of each field.
- Add the order service to the README's AI disclosure, and the usage log when asked.
- **Demo script:**
  1. Register two students → 100 / 100.
  2. A creates an errand for 15 → A has 85 available, 15 reserved.
  3. B and C accept at once → one gets 409.
  4. Pick up → deliver → complete → A 85 / 0, B 115.
  5. Complete again → 409.
  6. Stop credit-worker, then complete another errand → "credits processing", with the message visible in the
     RabbitMQ UI.
  7. Start credit-worker → the courier is paid.
  8. Let an accepted errand pass its deadline → EXPIRED, and the credits return to A.
  9. `GET /api/credits/admin/audit` → ok.

### Task 12: Frontend wiring
- **Files:** `types/order.ts`, `api/order.ts`, `update-request.tsx` (submit + edit mode), `explore.tsx`,
  `my-requests.tsx`, `my-tasks.tsx`, `task-card.tsx` / `task-details.tsx` (CTA handlers, "credits processing"
  badge), `utils/toolbar.ts` (remove the `pending` tab), and delete `utils/sample-task-cards.ts`.
- Use one mapper, `toTaskCard(errand, viewer)`. Map 422 field names onto the form's fields (`supplierId→supplier`,
  `latitude→location`, `deliverBy→deliveryBy`). Refresh the credit banner after create, cancel and complete.
- Cancel and Edit show only on OPEN errands, for the requester.
- When `supplier.active` is false, show "Supplier unavailable": hide Accept in Explore, and prompt the requester to
  cancel in My Requests (D13).
- Search waits 300 ms after typing stops and cancels the previous request, as on the Suppliers page. If
  `supplierSearch` is false, show a short note.
- **Check:** `npm run build`, `npm run lint`, then the demo script through the UI.

## Review focus

1. Actions racing expiry at the deadline (and complete racing it at `deliver_by + grace`): exactly one outcome, and
   the outbox matches it (Tasks 7 and 9).
2. Replies duplicated or out of order never move `credit_status` backwards (Task 8).
3. Supplier-service or user-service down during a list or create: lists still work with nulls; create fails cleanly
   with nothing written (Tasks 4 and 6).
4. A student editing their own delivery location changes their active errands, but can never edit someone else's
   location or a predefined one (Task 3).
5. `credit-demo` and `order-worker` competing for the same reply queue (Task 1 note).

## Open questions

None. All earlier questions are settled in section 1.
