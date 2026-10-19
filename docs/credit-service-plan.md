<!--
AI Assistance Disclosure:
Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
Scope: AI-written guide to the credit service's design, the order to build it in, and answers to the Part 2 and
       Part 4 review questions. Demo outputs are from runs of the implemented system.
Author review: reviewed by Aaron
-->

# Credit Service: how it's built and why

This guide walks through the Credit Service in the order it was built, and answers every question in the Part 2
(Credit Service) and Part 4 (Service Containerization) briefs. Each answer names the file that implements it, so you
can open the code while you explain.

- [1. The picture](#1-the-picture)
- [2. Decisions at a glance](#2-decisions-at-a-glance)
- [3. Why messages, not events](#3-why-messages-not-events)
- [4. Building it, step by step](#4-building-it-step-by-step)
- [5. Part 2 answers: Credit Service](#5-part-2-answers-credit-service)
- [6. Part 4 answers: Service Containerization](#6-part-4-answers-service-containerization)
- [7. For the Order Service](#7-for-the-order-service)
- [8. Demo script](#8-demo-script)
- [9. Known limits and next steps](#9-known-limits-and-next-steps)

---

## 1. The picture

```
                       ┌──────────── HTTP (read-only) ────────────┐
Browser ─▶ gateway :8080 ─▶ /api/credits/* ─▶ credit-service (API) ─┤
                       └─▶ /api/users/*   ─▶ user-service            │ reads
                                               │ outbox               ▼
                                               ▼                  credit-db (Postgres)
                                           RabbitMQ  ──credit.commands──▶ credit-worker ──writes──▶ credit-db
                                               ▲  │
                      order-service ─outbox────┘  └──credit.replies──▶ order-service
```

- **Writes** (anything that changes a balance) only travel as **command messages** through RabbitMQ, and only the
  credit-worker applies them.
- **Reads** (your balance, your history) are ordinary HTTP requests through the gateway.
- Each service owns its database. No service touches `credit-db` except the credit service.

## 2. Decisions at a glance

| Decision | Choice | One-line reason |
|---|---|---|
| Database | PostgreSQL (SQL) | Multi-row ACID transactions, row locks and CHECK constraints are exactly what a money-like ledger needs |
| Balance storage | `available` and `reserved` columns; `total` computed by Postgres | Overspending is checked on one column; `total` can never drift |
| History | Append-only `ledger_entries`, one row per change | Any balance can be re-derived and audited (N5.2.1) |
| Duplicate protection | Business keys: wallet = user id, reservation = errand id | A repeated message finds the first result instead of acting twice |
| How balance changes arrive | Command messages on RabbitMQ | One owner, one intended action, a reply, and no lost work when a service is down |
| Messages vs events | Messages (commands) | See [section 3](#3-why-messages-not-events) |
| Who may send what | One RabbitMQ login per service + topic permissions + broker-checked sender id | Enforced by the broker, not by trust |
| Delivery | At-least-once + idempotent handlers | Effect happens exactly once even if a message is delivered twice |
| User Service → credit | Transactional outbox | A registration and its wallet request are saved together or not at all |
| Initial allocation | 100 credits, `INITIAL_CREDITS`, owned by the credit service | Enough for several errands; small enough that people need to courier |
| Containers | One image per service; API and worker are separate containers from it | They scale and restart independently |

## 3. Why messages, not events

Both are things sent through a broker. The difference is what they mean and who they're for
(*Enterprise Integration Patterns*, Hohpe and Woolf: "Command Message" vs "Event Message"):

| | Event | Message (command) |
|---|---|---|
| Says | "This happened": `ErrandCompleted` | "Do this": `TransferCredits {errand 42, requester 7 → courier 9}` |
| Addressed to | Nobody in particular; any number of subscribers | Exactly one receiver that owns the action |
| Sender expects | Nothing | The action to happen, and an answer |
| Who decides what it means | Each subscriber | The receiver's contract, which the sender follows |

**Why every balance change in CampusRun is a message:**

1. **There's exactly one rightful handler.** Only the credit service may change a wallet. A command names that
   receiver and that one action. With an `ErrandCompleted` event, the payout would be a side effect the credit
   service *infers*, and the rules for when money moves would be hidden inside its reading of another service's events.
2. **The sender needs an answer.** A reserve can fail (not enough credits). The Order Service must know, so it can
   publish the errand or tell the requester. A command gets a reply (`ReservationResult`, matched by
   `correlation_id`); an event, by definition, has no one obliged to answer.
3. **The message carries everything needed to act.** `TransferCredits` names the errand, requester and courier. The
   credit service doesn't need to know the errand state machine, so the Order Service can add states (`PICKED_UP`,
   disputes...) without the credit service changing.
4. **It can be secured per action.** We can say "only the Order Service may send `TransferCredits`" and have
   RabbitMQ enforce it. With events, anyone allowed to publish `ErrandCompleted` would indirectly trigger a payout.
5. **Point-to-point delivery is what we want.** One queue, consumed by one service (with as many worker copies as we
   like, each message going to exactly one of them). Fan-out to many subscribers, the strength of events, isn't needed.

**What we give up:** the sender is coupled to knowing the credit service exists and its command names. That's
acceptable: an errand can't exist without credits, so the Order Service depends on the credit service anyway. If
later something only needs to *react* (e.g. a notification service), that's where an event would fit.

**Why asynchronous instead of a direct HTTP call?** If completing an errand called `POST /transfer` and the credit
service was down, the completion would fail, or the order would be completed with no payout and nothing left to
retry. With a durable queue, the command waits until the credit service is back (drill A in section 8), and the
broker spreads load across workers.

**Why RabbitMQ (a message broker)?** It's built for exactly this: durable queues, per-message acknowledgement,
redelivery, dead-letter queues, per-user permissions and publisher confirms. Kafka is a replayable event log,
which is useful for streams of events, but heavier than 2,000 errands a day needs, and per-message acks and
dead-lettering would have to be built on top. Redis Streams is lighter but has weaker durability by default and no
equivalent of per-routing-key permissions.

## 4. Building it, step by step

This is the order to build (or explain) it in. Each step only depends on the ones before.

### Step 1: Choose the database → PostgreSQL

See [5.1](#51-database-choice-and-credit-data-model) for the full justification. In short: a transfer changes two
wallets, a reservation and two ledger rows, and all five must change together. That's a multi-row ACID transaction,
and Postgres also gives row locks, unique keys and CHECK constraints to enforce the rules in the database itself.

### Step 2: Design the tables → [`tables.py`](../credit-service/src/credit_service/tables.py)

Three tables (migration: `credit-service/migrations/versions/c7c98df02645_...py`):

```
wallets                                   reservations                         ledger_entries (append-only)
──────────────────────────────            ───────────────────────────          ──────────────────────────────
user_id    int  PK  (user-service id)     errand_id     int PK (order id)      id              bigint PK
available  int  CHECK >= 0                requester_id  int                    user_id         int FK→wallets
reserved   int  CHECK >= 0                courier_id    int  (set on transfer) errand_id       int  (null: allocation)
total      int  GENERATED (avail+res)     amount        int  CHECK > 0         kind            INITIAL_ALLOCATION |
created_at, updated_at                    status  HELD|TRANSFERRED|              RESERVE | RELEASE |
                                                  RELEASED|REJECTED              TRANSFER_OUT | TRANSFER_IN
                                          reason        e.g. EXPIRED           available_delta, reserved_delta
                                          revision      int (reward changes)   available_after, reserved_after
                                          created_at, updated_at               message_id      (the command)
                                                                               created_at
```

Rules Postgres enforces, whatever the code does:

- `available >= 0` and `reserved >= 0`: nothing can commit a negative balance.
- `total` is a generated column, so it is always exactly `available + reserved`.
- One wallet per user (primary key) and **at most one `INITIAL_ALLOCATION` per user** (partial unique index).
- One reservation per errand (primary key).
- Each ledger `kind` can only move credits its own way, e.g. `RESERVE` must have `reserved_delta = -available_delta`,
  and only `INITIAL_ALLOCATION` can add credits overall (`ck_ledger_entries_kind_moves`).
- A reservation has a courier exactly when it's `TRANSFERRED`, and the courier isn't the requester.

There are no foreign keys to users or errands, because those live in other services' databases.

### Step 3: Write the operations → [`ledger.py`](../credit-service/src/credit_service/ledger.py)

Five functions, each run inside **one** transaction, and each safe to run twice:

| Operation | What happens | Why a repeat is harmless |
|---|---|---|
| `open_wallet` | Insert wallet with 100 available + ledger `INITIAL_ALLOCATION` | Insert is `ON CONFLICT DO NOTHING`; the allocation is only written if the row was created |
| `reserve` | Claim the errand row, then `UPDATE wallets SET available -= x, reserved += x WHERE available >= x`, then ledger `RESERVE` | The errand row already exists, so it returns the first result |
| `adjust` | Move the difference between available and reserved, if `revision` is newer | Same or older revision: no change |
| `transfer` | Requester `reserved -= x`, courier `available += x`, two ledger rows, status `TRANSFERRED` | Only a `HELD` reservation can be transferred |
| `release` | Requester `reserved -= x, available += x`, ledger `RELEASE`, status `RELEASED` | Only a `HELD` reservation can be released |

Three details matter when someone asks "what if two things happen at once?":

- **The balance check is inside the UPDATE** (`... WHERE available >= amount`). Postgres locks the row for the
  update, so there's no gap between "check" and "debit" for another transaction to spend the same credits.
  The test `test_concurrent_reserves_never_overspend` fires 40 reserves of 7 at a 100-credit wallet at once: exactly 14 succeed.
- **Locks are always taken in the same order**: the reservation row, then wallets by ascending user id. Two
  transfers in opposite directions between the same two users can't deadlock (`test_cross_transfers_...`).
- **A rejected reserve is recorded** (status `REJECTED`, reason `INSUFFICIENT_CREDITS`), not forgotten. If the same
  message arrives again after the requester has earned more credits, it still says "rejected", because the Order
  Service already told the requester it failed.

### Step 4: Define the message contract → [`commands.py`](../credit-service/src/credit_service/commands.py)

Five commands (table in [5.4](#54-integration-and-consistency)), each a Pydantic model that rejects unknown fields and
non-positive ids or amounts, each with its allowed sender. One reply type, `ReservationResult`, describes the
*current state* of the errand's credits (status, amount, courier) plus `rejection` if this particular command changed
nothing. Because it describes state rather than "what I just did", a repeated or late reply is harmless.

### Step 5: Set up the broker → [`rabbitmq/definitions.json`](../rabbitmq/definitions.json) and [`provision.sh`](../rabbitmq/provision.sh)

```
credit.commands (topic exchange)
   ├─ wallet.open       ┐
   └─ reservation.*     ┴─▶ credit-service.commands (quorum queue, delivery limit 5)
                                   └─ dead letters ─▶ credit.dead-letter ─▶ credit-service.commands.dead
credit.replies (direct exchange)
   └─ order-service ──────▶ order-service.credit-replies (quorum queue)
```

- **Quorum queues** are RabbitMQ's replicated, always-durable queue type, recommended for data that must not be lost.
  Messages are published as persistent and stored in the `rabbitmq-data` volume.
- **One login per service.** `provision.sh` (the container's entrypoint) creates `credit-service`, `user-service` and
  `order-service` logins from `.env`, then loads `definitions.json`. Permissions:

| Login | May publish | May read |
|---|---|---|
| `user-service` | `credit.commands`, routing key `wallet.open` only | nothing |
| `order-service` | `credit.commands`, routing keys `reservation.(reserve\|adjust\|transfer\|release)` only | its own `order-service.*` queues |
| `credit-service` | `credit.replies` only | `credit-service.commands` only |

  None of them can create or change the queues (configure permission is empty), so a bug can't remove the
  dead-letter settings. The default `guest/guest` account is never created.

### Step 6: Write the worker → [`worker.py`](../credit-service/src/credit_service/worker.py)

For each message, in this order:

1. **Check it.** Known `type`; the sender (`user_id`, which RabbitMQ has already verified matches the login) is
   allowed to send it; routing key matches; body is valid. If not → dead-letter queue.
2. **Apply it** in one transaction (`ledger.apply`). If the database is unreachable or a lock conflict happens,
   keep the message and retry with backoff (0.5s up to 30s) until it works. Other errors: 3 tries, then dead-letter.
3. **Reply** to the sender, waiting for RabbitMQ's publisher confirm.
4. **Acknowledge** the command.

The acknowledgement is **last**. If the worker dies at any point before it, RabbitMQ delivers the command again,
and the idempotent operation turns the repeat into "same result, no change". At-least-once delivery plus idempotent
handling gives an effect that happens exactly once.

Two RabbitMQ behaviours we tested on 4.3.6 and designed around:

- A message the worker rejects with `nack(requeue=True)` is **not** counted towards the delivery limit, so it would
  loop forever (we saw 600 redeliveries in a few seconds). The worker therefore never requeues; it retries in place.
- A worker that **crashes** while holding a message **does** count. After 5 redeliveries the message goes to the
  dead-letter queue, so a message that crashes the worker can't crash it forever.

### Step 7: Add the read-only API → [`main.py`](../credit-service/src/credit_service/main.py), [`routes/`](../credit-service/src/credit_service/routes)

`GET /wallets/me`, `/wallets/me/transactions`, `/reservations/{errandId}`, `/admin/audit` (table in the
[README](../credit-service/README.md#api)). Same JWT check as the supplier service. `GET /wallets/me` returns
`status: "PENDING"` (not 404) for a user whose wallet hasn't been opened yet, so the web app can say "on its way".
A test asserts the API only has `GET` routes, so no HTTP request can create, buy or withdraw credits (F14.1.1).

### Step 8: Connect the User Service → [`user-service/src/user_service/outbox.py`](../user-service/src/user_service/outbox.py)

Registration inserts the user **and** an `OpenWallet` row in the `outbox` table in the same transaction. A
background task (`OutboxRelay`) publishes unsent rows every second and marks each one sent once RabbitMQ confirms it.
`create-initial-admin` does the same, since admins keep every student capability. Details in [5.2](#52-initial-credit-allocation).

### Step 9: Show it in the web app → [`credit-banner.tsx`](../frontend/src/components/shared/credit-banner.tsx)

The banner on Explore, My Tasks and My Requests now shows the real balances. While the wallet is `PENDING`, it shows
a **Pending** pill and "Your starter credits are on their way", and checks every 2 seconds (otherwise every 15) until
the numbers arrive, without a reload. It also takes a `pending` prop for the Order Service to switch on while a
transfer or release is in flight ([section 7](#7-for-the-order-service)). Checked at 1280px and 390px wide.

### Step 10: Containerise, test, audit

The `credit-db`, `credit-migrate`, `credit-service`, `credit-worker` and `rabbitmq` containers ([section 6](#6-part-4-answers-service-containerization)),
59 tests (85% line coverage of the service, excluding the demo tool; N9.2.1 asks for 70%), and `credit-audit`, which checks the invariants against the live
data ([audit.py](../credit-service/src/credit_service/audit.py)).

---

## 5. Part 2 answers: Credit Service

### 5.1 Database choice and credit data model

**Which database, and why?** PostgreSQL, a relational (SQL) database.

- **The queries are relational.** Look up one wallet by user id (primary key); list a user's history newest first
  (index on `user_id, id`); list an errand's credit movements (index on `errand_id`); and audit queries that join
  wallets to `SUM`s of the ledger and of held reservations. These are ordinary SQL with joins and aggregates.
- **Concurrent updates.** Many requests can hit one wallet at once (two errands posted together, a payout arriving
  while the user posts). Postgres row locks serialise updates to the same wallet, a conditional `UPDATE ... WHERE
  available >= x` makes check-and-debit one atomic step, and unique keys make a duplicate insert wait and then see
  the first one.
- **Consistency.** A transfer changes two wallets, a reservation and two ledger entries. All five must change together
  or not at all, which is what a multi-row ACID transaction gives. CHECK constraints, a generated column and a partial
  unique index enforce the rules even if the code has a bug.
- **Why not NoSQL?** A document store such as MongoDB can update one wallet document atomically, but a transfer spans
  several documents, so it would need multi-document transactions, and rules like "never negative" or "one allocation
  per user" would live only in application code. Redis is fast but not built for durable, constrained financial
  records. NoSQL's strength, horizontal scaling of huge or schema-less data, isn't needed: peak load is 10,000 users
  and 2,000 errands a day. The rest of the team also uses Postgres, so we share tooling.

**The schema** is in [Step 2](#step-2-design-the-tables--tablespy).

**How are reserved and total stored, and kept consistent?**

- `available` and `reserved` are stored. `total` is a **generated column** (`GENERATED ALWAYS AS (available + reserved) STORED`):
  Postgres computes it on every write, so it can't disagree with the other two.
- We store `available` (not just `total`) because it's the number every reserve checks. "Do you have enough?" is then
  one column and one CHECK constraint (`available >= 0`).
- Every change to a wallet is a single `UPDATE` that moves credits between columns (e.g. `available = available - 15,
  reserved = reserved + 15`), in the same transaction as the matching ledger entry and reservation row.
- Two invariants are checked by `credit-audit` / `GET /admin/audit`: each wallet's balances equal the sum of its ledger
  entries, and each wallet's `reserved` equals the total of its `HELD` reservations. A third: credits in circulation
  equal credits ever allocated. A test changes a balance behind the ledger's back and checks the audit catches it.

### 5.2 Initial credit allocation

**How much, and how is it configured?** **100 credits**, set by `INITIAL_CREDITS` (default 100) in the credit
service's settings ([config.py](../credit-service/src/credit_service/config.py), passed in `compose.yaml`).

- **Why 100?** Rewards are 1–100 credits (F7.1.1). A typical errand (lunch from a canteen, a print job) is likely
  5–20 credits, so 100 lets a new student post 5–10 errands before they need to earn any. That's enough to really use
  the platform, and still small enough that people need to courier to keep requesting, which is what keeps errands
  getting picked up.
- **Why is it the credit service's setting, not the User Service's?** It's credit-economy policy. The User Service only
  says "open a wallet for user 7"; it never sends an amount, so it can't grant more than the policy allows. The amount
  granted is recorded on the ledger entry, so changing the setting later only affects new wallets, and the audit still
  balances.

**How is it granted during registration?**

```
POST /api/users/auth/register
  └─ user-service, one transaction:  INSERT users ...  +  INSERT outbox (OpenWallet {userId: 7})  → COMMIT → 201
OutboxRelay (≤1s later):             publish to credit.commands / wallet.open, user_id=user-service
                                     wait for RabbitMQ's confirm → mark the outbox row published
credit-worker, one transaction:      INSERT wallets (7, available 100) ON CONFLICT DO NOTHING
                                     + ledger INITIAL_ALLOCATION +100        → COMMIT → ack
GET /api/credits/wallets/me:         PENDING ... then ACTIVE, available 100
```

Measured in the Compose stack: both new users went from `PENDING` to `ACTIVE 100` within 0.3 seconds.

**What if registration succeeds but the wallet is delayed or fails?**

| What goes wrong | What happens |
|---|---|
| RabbitMQ is down | Registration still succeeds (it never talks to RabbitMQ). The `OpenWallet` row waits in the outbox; the relay retries with backoff and records `attempts` and `last_error`. When RabbitMQ is back, it's published. Tested: wallet opened ~12s after the broker restarted. |
| user-service crashes right after the commit | The row is committed, so the relay publishes it after restart. |
| user-service crashes after publishing, before marking it sent | The relay publishes it again. The credit service sees the wallet already exists and does nothing. |
| The credit worker or its database is down | The message waits in the durable queue (or is held and retried by the worker) until it can be applied. |
| Meanwhile, the user opens the app | The banner shows **Pending** ("your starter credits are on their way") and updates by itself. |
| Meanwhile, the user tries to post an errand | The credit service rejects the reserve with `NO_WALLET`, and the Order Service can say "your credits are still being set up". Nothing is held. |
| A message is lost anyway (e.g. the credit database is restored from an old backup) | `resync-wallets` in user-service queues `OpenWallet` for every user. It's safe to run any time (see the next question). |
| Users who registered before this existed | The migration that added the outbox queued `OpenWallet` for all of them. |

What we deliberately **don't** do is publish straight to RabbitMQ after the commit (a crash in between loses the
message) or before it (a rolled-back registration would still get a wallet). The outbox closes both gaps.

**How do we stop the same user getting the initial allocation twice?** Three layers:

1. `wallets.user_id` is the primary key, and the insert is `ON CONFLICT DO NOTHING`. The allocation ledger entry is
   written only if that insert created the row, in the same transaction.
2. A partial unique index allows at most one `INITIAL_ALLOCATION` ledger entry per user, so even buggy code can't
   commit a second one (`test_database_refuses_a_second_allocation_even_without_the_code`).
3. The User Service never sends an amount, and no HTTP endpoint grants credits.

Tested: 20 `OpenWallet` messages for one user processed concurrently → one wallet, one allocation, 100 credits.

**Demonstration:** `docker compose run --rm credit-demo register` (or register in the web app and watch the banner).

### 5.3 Reservation, transfer, and release

**Are updates atomic?** Yes. Each command runs in one database transaction (`async with engine.begin()` in the
worker), which commits the wallet change(s), the reservation and the ledger entries together, or rolls all of them
back. The message is acknowledged only after the commit.

**How are credits reserved when an order is placed?** The correct sequence, across both services:

```
1. Order Service, one transaction:  INSERT errand (state PENDING)  +  outbox ReserveCredits {errand, requester, amount}
2. credit-worker, one transaction:
     a. INSERT reservation (errand, HELD) ON CONFLICT DO NOTHING      ← claims the errand; a duplicate stops here
     b. UPDATE wallets SET available -= amount, reserved += amount
          WHERE user_id = requester AND available >= amount           ← check and debit in one statement
     c. if b changed no row → reservation REJECTED (INSUFFICIENT_CREDITS or NO_WALLET)
        else               → ledger RESERVE (-amount available, +amount reserved)
     d. COMMIT, reply ReservationResult, ack
3. Order Service: HELD → errand OPEN (now visible to couriers);  REJECTED → tell the requester why
```

- **How is sufficient balance checked?** By the `WHERE available >= amount` inside the `UPDATE` (2b). There's no
  separate SELECT, so nothing can spend the credits between checking and taking them. `CHECK (available >= 0)` is a
  second guard.
- **How are reserved credits kept from funding another order?** Reserving *moves* them from `available` to
  `reserved`, and only `available` is ever checked or spent (F12.1.2). They're also tied to one errand by the
  reservation row, and only that errand's transfer or release can move them again.
- **Why claim the errand row first (2a)?** If the same reserve arrives twice at the same moment (redelivery, two
  workers), the second insert waits on the primary key, then sees the first and returns its result, so the requester
  is charged once.
- **Why does the Order Service create the errand before reserving (step 1)?** So credits are never held for an errand
  that doesn't exist (see [5.4](#54-integration-and-consistency)), and the errand stays `PENDING` (not visible to couriers)
  until it's funded (F7.2).

**Transfer after completion** (`TransferCredits`), one transaction:

```
lock reservation (must be HELD) → lock requester and courier wallets, lower user id first
requester: reserved -= amount           ledger TRANSFER_OUT (0, -amount)
courier:   available += amount          ledger TRANSFER_IN  (+amount, 0)
reservation: TRANSFERRED, courier_id    → COMMIT
```

It pays the **held** amount (so a reward changed with `AdjustReservation` is paid correctly). It only works from
`HELD`, so a repeat returns "already TRANSFERRED to this courier" and moves nothing (F13.1.1).

**Release after cancel or expiry** (`ReleaseCredits`): requester `reserved -= amount, available += amount`, ledger
`RELEASE`, reservation `RELEASED` with reason `CANCELLED` or `EXPIRED`. Also only from `HELD`; nothing goes to a
courier (F13.2.1). Transfer and release can't both happen: whichever commits first wins, and the other gets
`ALREADY_TRANSFERRED` or `ALREADY_RELEASED` (`test_racing_transfer_and_release_settle_exactly_once`).

**Balances before and after** (from `credit-demo scenario 2 3`, run against the Compose stack):

```
1. Requester posts errand with a 15-credit reward
  Before:  user 2  available 100  reserved  0  total 100     user 3  available 100  reserved 0  total 100
  <- HELD, amount 15
  After:   user 2  available  85  reserved 15  total 100   (-15 available, +15 reserved)

2. The same reserve message is delivered twice more            → both replies HELD 15; balances unchanged
3. Requester raises the reward to 20 (AdjustReservation)       → user 2: available 80, reserved 20

4. Errand COMPLETED: TransferCredits
  Before:  user 2  available  80  reserved 20  total 100     user 3  available 100  reserved 0  total 100
  <- TRANSFERRED, amount 20, courier 3
  After:   user 2  available  80  reserved  0  total  80     user 3  available 120  reserved 0  total 120

5. The transfer is redelivered                                 → TRANSFERRED; both wallets unchanged

6. New errand for 30, then it EXPIRES: ReleaseCredits
  Before:  user 2  available  50  reserved 30  total  80
  <- RELEASED, amount 30, reason EXPIRED
  After:   user 2  available  80  reserved  0  total  80

7. New errand for 100 with only 80 available                  → REJECTED, INSUFFICIENT_CREDITS; unchanged

Audit: OK | 300 credits allocated, 300 in circulation
```

### 5.4 Integration and consistency

**The Credit Service's interfaces, and who may use each:**

| Interface | Kind | Who may call it | Enforced by |
|---|---|---|---|
| `OpenWallet` | command | User Service only | RabbitMQ topic permission (`user-service` may only publish `wallet.open`) + worker checks the broker-verified `user_id` |
| `ReserveCredits`, `AdjustReservation`, `TransferCredits`, `ReleaseCredits` | command | Order Service only | Same: `order-service` may only publish `reservation.*`; the worker checks `user_id` |
| `ReservationResult` | reply | Sent by the credit service only, to the command's sender | Only `credit-service` may publish to `credit.replies`; the reply carries `user_id=credit-service` for the receiver to check |
| `GET /wallets/me`, `GET /wallets/me/transactions` | HTTP | Any signed-in user, own wallet only | JWT; the user id comes from the token, never from the request |
| `GET /reservations/{errandId}` | HTTP | That errand's requester or courier, or an admin | JWT; others get 404 |
| `GET /admin/audit` | HTTP | Admins | JWT `role` claim |

We tested the broker side directly: `user-service` publishing `reservation.reserve` is refused (`ACCESS_REFUSED`),
`user-service` claiming to be `order-service` is refused (`PRECONDITION_FAILED`), and `credit-service` can't read
the Order Service's queue. A message with no sender, or an allowed key carrying a forbidden command type, reaches
the worker and is dead-lettered.

**When an operation succeeds in one service but the related one fails in another:**

*"Credits are reserved, but order creation fails."* Our sequence makes this impossible: the reserve command only
exists because the errand row was committed with it (outbox, step 1 above). If order creation fails, its transaction
rolls back and takes the reserve command with it. The opposite case, an errand that's created but never funded, is
handled: it stays `PENDING`, invisible to couriers, until the reply arrives. If the requester cancels it first, the
Order Service sends `ReleaseCredits`. If that release overtakes the reserve, the credit service records a
`REJECTED / CANCELLED_BEFORE_RESERVE` placeholder, so the late reserve holds nothing
(`test_release_that_overtakes_its_reserve_cancels_it`).
(With the alternative, reserving over HTTP first and then creating the order, a failure in between would leave
credits held for nothing. That's why the order is created first.)

*"An order is completed while credit transfer is temporarily unavailable."* The Order Service commits `COMPLETED`
and the `TransferCredits` command together. The command waits (in the Order Service's outbox if RabbitMQ is down,
or in the durable queue if the credit service is down) and is applied when the credit service is back. Meanwhile the
errand is `COMPLETED` with payment pending, and the web app shows **Pending** on the wallet banner. Tested (drill A):
with the worker stopped, a reserve and a transfer sat in the queue and balances didn't move; after restarting the
worker, both were applied in order and the courier was paid once.

**How incomplete cross-service operations are detected and resolved:**

| Where it can get stuck | How it's detected | How it's resolved |
|---|---|---|
| Sender's outbox (RabbitMQ unreachable) | `outbox` rows with `published_at IS NULL`, `attempts`, `last_error` | Relay retries automatically with backoff |
| Command queue (credit service down) | Queue depth in the RabbitMQ management UI | Applied automatically when the worker is back |
| Worker can't reach its database | Worker log "Database unavailable", message held | Retried until the database is back (tested: applied within seconds of Postgres restarting) |
| Invalid or poison message | `credit-service.commands.dead` count in the management UI, worker log line with the reason | A person inspects it, fixes the cause, and moves it back (management UI "Move messages", or `resync-wallets` for wallets) |
| A reply never arrived (Order Service side) | Errand with `credit_status` still `RESERVING` / `TRANSFERRING` / `RELEASING` after 2 minutes | Order Service's reconciler re-sends the same command; idempotency makes that safe ([section 7](#7-for-the-order-service)) |
| Credits held for an errand that ended | `credit-audit` lists holds older than 48 hours (no errand can stay open that long) | Order Service checks the errand and sends the missing transfer or release |
| Balances don't add up | `credit-audit` (exit code 1) / `GET /admin/audit` | Investigate; the ledger shows every change and which message caused it |

---

## 6. Part 4 answers: Service Containerization

### 6.1 Containerization strategy

**The containers** ([compose.yaml](../compose.yaml)):

| Service | Containers | Image |
|---|---|---|
| User | `user-db`, `user-migrate` (one-off), `user-seed-admin` (one-off), `user-service` | `user-service/Dockerfile` |
| Supplier | `supplier-db`, `supplier-migrate` (one-off, migrates + seeds), `supplier-service` | `supplier-service/Dockerfile` |
| Credit | `credit-db`, `credit-migrate` (one-off), `credit-service` (API), `credit-worker`, `credit-demo` (on demand) | `credit-service/Dockerfile` |
| Order | `order-service` (AI autofill only for now; no database yet) | `order-service/Dockerfile` |
| Web app | `frontend` | `frontend/Dockerfile` |
| Infrastructure | `rabbitmq`, `gateway` | pre-built images |

**Dockerfile strategy (Python services)**, following Docker's
[building best practices](https://docs.docker.com/build/building/best-practices/):

- **Runtime:** `python:3.14.7-slim`, pinned to the same Python as `.python-version`; slim keeps the image small.
- **Dependencies:** the `uv` binary is copied from a pinned image (`ghcr.io/astral-sh/uv:0.12.7`). `pyproject.toml`
  and `uv.lock` are copied first and installed with `uv sync --locked --no-dev`, so that layer is cached until the
  lockfile changes; then the code is copied and the project installed. `--locked` fails the build if the lockfile is
  out of date, and `--no-dev` leaves test tools out. A BuildKit cache mount speeds up rebuilds.
- **Build steps:** bytecode is compiled at build time for faster start-up. `.dockerignore` keeps `.env`, virtualenvs
  and test output out of the build context, so secrets can't end up in an image.
- **Startup:** runs as an unprivileged user (`app`). The default command starts the API on `${PORT:-8000}`, which
  works locally and on Cloud Run. The same image runs other commands: `credit-worker`, `alembic upgrade head`,
  `credit-audit`, `credit-demo`. One image per service means what you test is what you deploy.
- **Frontend:** a two-stage build: Node compiles the app, then only the static files are copied into `nginx`.

**Pre-built images (sources acknowledged):**

| Image | Source | Used for |
|---|---|---|
| `postgres:18` | Docker Official Image, https://hub.docker.com/_/postgres | `user-db`, `supplier-db`, `credit-db` |
| `rabbitmq:4.3.6-management` | Docker Official Image, https://hub.docker.com/_/rabbitmq (the `-management` variant adds the management UI and HTTP API) | `rabbitmq`, configured by mounting `provision.sh` and `definitions.json`; the image itself is unchanged |
| `nginx:stable-alpine` | Docker Official Image, https://hub.docker.com/_/nginx | `gateway`, and the `frontend` runtime stage |
| `python:3.14.7-slim`, `node:24.18.0-alpine` | Docker Official Images, https://hub.docker.com/_/python, https://hub.docker.com/_/node | Base images for our own Dockerfiles |
| `ghcr.io/astral-sh/uv:0.12.7` | Astral's official uv image, https://github.com/astral-sh/uv | The uv binary copied into our images |

**How it supports independent development and deployment:**

- Each service has its own folder, Dockerfile, lockfile, database and migrations. `docker compose up --build credit-service`
  rebuilds only that one; a change to the credit service never rebuilds the others (N9.1.1).
- Services meet only at **contracts**: HTTP through the gateway, and messages whose schema the receiver owns
  (`commands.py`). The Order Service was added later (its autofill endpoint) without changing the credit service, and
  its errand flow can be added the same way.
- The API and the worker are separate containers from one image. Scale the worker alone
  (`docker compose up --scale credit-worker=3` shares the queue across three workers; tested with 60 concurrent reserves:
  all three workers took part, and the wallet was never overspent) or restart it without touching the API.
- Nice-to-haves follow the same pattern. AI autofill (natural-language errand creation) is an endpoint in
  `order-service`, with its Groq key supplied only to that container; real-time chat could be its own folder and
  container, with its own RabbitMQ login if it needs to send messages. The interactive map is frontend plus supplier
  data, so it needs no new container. Cloud deployment reuses the same images with different
  configuration.

### 6.2 Dependency, configuration, and data management

**Reproducible environments:**

- Python packages: each service's `uv.lock` pins every package to an exact version with hashes; `uv sync --locked`
  refuses to build from a stale lockfile.
- Python itself: `.python-version`, `mise.toml` and the base image tag all say 3.14.7. uv is pinned to 0.12.7.
- Frontend: `package-lock.json` with `npm ci`, Node pinned in `mise.toml` and the base image.
- Infrastructure images are pinned by tag (RabbitMQ to the exact `4.3.6`). Suggestion: pin `postgres:18` to an exact
  minor such as `postgres:18.6` too, to meet N9.1.2 strictly.

**How configuration is supplied:** environment variables, read by `pydantic-settings` (`config.py` in each service).
Compose builds them from the root `.env` file: `${VAR:?message}` stops `docker compose up` with a clear message if a
required secret is missing. Each container gets only what it needs:

| Container | Gets | Doesn't get |
|---|---|---|
| `credit-service` (API) | DB URL, `JWT_SECRET` | any RabbitMQ login |
| `credit-worker` | DB URL, `credit-service` RabbitMQ login | `JWT_SECRET` (the API refuses to start without it; the worker doesn't need it) |
| `user-service` | its DB URL, `JWT_SECRET`, `user-service` RabbitMQ login | other services' passwords |

**How secrets stay out of code, images and logs:**

- **Code:** `.env` is git-ignored; `.env.example` lists every variable with empty secret values.
- **Images:** `.dockerignore` excludes `.env`, and no secret is passed as a build argument, so images contain no
  secrets and the same image works in every environment.
- **Logs:** secrets are `SecretStr`, which prints as `**********`; the worker logs only error types for connection
  failures, never URLs; and the AMQP client masks passwords (`amqp://credit-service:******@...`).
- **Broker:** each service has its own RabbitMQ password, so one leak doesn't expose the others; `guest/guest` is never created.
- **Honest limit:** environment variables are visible to anyone who can run `docker inspect` on the host. That's fine
  for local development; a cloud deployment should use the platform's secret manager (part of the CI/CD nice-to-have).

**Database initialisation, schema changes, seed data, persistence:**

- **Initialisation and schema changes:** Alembic migrations in each service. A one-off `*-migrate` container runs
  `alembic upgrade head` and exits; the service only starts after it succeeds (`service_completed_successfully`).
  A schema change is a new migration file; already-applied ones are skipped (Alembic's version table). Migrations run
  as a separate step rather than at app start-up, so several instances of a service never race to migrate.
- **Seed data:** suppliers and delivery locations are loaded by `supplier-migrate` from CSV; the first admin by
  `user-seed-admin`. The credit service has no seed data: wallets come only from registrations. The outbox migration
  queued `OpenWallet` for users who already existed.
- **Persistent storage:** named volumes `user-db-data`, `supplier-db-data`, `credit-db-data` and `rabbitmq-data`.

**What happens to data when containers stop, restart, or are recreated?**

| Action | Database data | Queued messages |
|---|---|---|
| `docker compose stop` / `start`, or a crash and restart | Kept | Kept |
| `docker compose down`, then `up` (containers recreated) | Kept (volumes survive) | Kept |
| `docker compose down -v` | **Deleted**: fresh empty databases next time | **Deleted** |

Tested (drill C): with the worker stopped, a reserve was queued, then everything was removed with `docker compose down`
and started again. Balances were intact and the queued reserve was applied after the restart.
For RabbitMQ this needs one extra setting, `hostname: rabbitmq`: RabbitMQ stores its data under its node name, which
includes the hostname. A recreated container with a random hostname would look in a different folder and start empty.

### 6.3 Service communication and startup

**How services find each other:** Compose puts all containers on one private network with DNS by service name.
Services connect to `credit-db:5432`, `rabbitmq:5672`, `user-service:8000`, and so on; for example, `order-service`
calls `http://supplier-service:8000` to match a supplier name during autofill. No IP addresses are configured.

**Separating external from internal communication:**

- **External** traffic has one door: the `gateway` (nginx) is the only container with a public port (`8080`). It
  serves the web app and routes `/api/<service>/...` to each service. The services' own ports are never published.
- **Internal** traffic is service-to-service on the private network: commands and replies over RabbitMQ, each service
  with its own login and permissions. The browser can't reach RabbitMQ, the databases or the worker.
- Databases and RabbitMQ are also published on `127.0.0.1` only, for developer tools on your own machine; that's not
  reachable from other machines. A deployment would drop those.
- Even through the gateway, the credit API is read-only, so the outside world has no way to change a balance.
- A further step, if the mentor asks: give Compose two networks, `public` (gateway, frontend) and `internal`
  (everything else, with `internal: true`), with only the gateway on both.

**Startup dependencies:**

| Situation | What happens |
|---|---|
| A service starts before its database | Prevented at start-up: `*-migrate` waits for the database's healthcheck (`pg_isready`), and the service waits for migrations to finish. |
| The worker starts before RabbitMQ | Prevented: it waits for `rabbitmq` to be healthy, which only happens once `provision.sh` has created the logins and queues. If it starts anyway (e.g. run by hand), it retries the connection with backoff (1s up to 30s). |
| user-service starts before RabbitMQ | Allowed on purpose: registration doesn't need RabbitMQ; the outbox waits. |
| RabbitMQ restarts while running | The worker's robust connection reconnects and resumes consuming by itself (tested). Unacknowledged messages are redelivered. |
| The credit database goes down while running | The worker holds the current message and retries until it's back (tested); the API returns 503 on `/health` and reconnects afterwards (`pool_pre_ping`). |
| The worker crashes | `restart: unless-stopped` brings it back; its unacknowledged message is redelivered. |
| `credit-service` is rebuilt or recreated and gets a new IP address | The gateway looks the name up again every 10 seconds (`resolver 127.0.0.11 valid=10s`, the same pattern as the orders route), so it finds the new container without a gateway restart. Tested by forcing a new IP. The users and suppliers routes still resolve once at gateway start-up, so they return 502 after their container moves until the gateway restarts; the same change would fix them. |

**How Compose coordinates it, reproducibly:** `depends_on` with conditions (`service_healthy`,
`service_completed_successfully`), healthchecks on Postgres and RabbitMQ, and one-off containers for migrations
and seeding. From a clean checkout:

```
cp .env.example .env        # fill in the passwords and JWT_SECRET
docker compose up --build   # everything, in the right order
```

### 6.4 Deployment demonstration and CI/CD considerations

Local deployment is the Compose stack above (the demo in [section 8](#8-demo-script)). Choices made with cloud and CI/CD in mind:

- **Build once, configure per environment.** Images have no secrets or environment-specific values, and the API
  listens on `$PORT`, so the same image runs on Cloud Run or Kubernetes.
- **Migrations are a separate job**, not part of app start-up, so they map directly onto a Cloud Run job or a
  Kubernetes Job run once per deploy.
- **The worker is its own deployment**, scaled by queue depth, independently of the API.
- **Rolling deploys are safe.** A worker stopped mid-message loses nothing (the message is redelivered and the repeat
  is harmless), and the outbox keeps messages while the broker is being replaced.
- **Health endpoints** (`/health`) for load-balancer and orchestrator probes; API docs off unless `ENABLE_DOCS=true`.
- **CI:** each service's tests run on their own against a Postgres service container (`uv run pytest`); the
  credit tests don't need RabbitMQ. The frontend runs `npm run build` and lint. A pipeline can build only the services
  whose folders changed.
- **Broker topology is code** (`rabbitmq/definitions.json`), reviewed like any other change. In the cloud, a managed
  RabbitMQ (e.g. CloudAMQP or Amazon MQ) can load the same definitions, with TLS (`amqps://`) for N8.1.1.

---

## 7. For the Order Service

What the Order Service needs to do so the credit flow works end to end. The credit side is done and testable now
with `credit-demo`, which sends exactly the messages below.

The current `order-service` only provides AI autofill for the create-request form: it has no database and doesn't
create errands. Its autofill suggests a reward of 1–100 credits, which matches F7.1.1; when the form is submitted, that
is the "Created" row in step 3.

**1. Errand states.** Add `PENDING` (created, waiting for credits) before `OPEN`, and a way to end an unfunded errand
(e.g. `REJECTED`, or `CANCELLED` with a reason). Only `OPEN` errands appear on Explore (F7.2). The frontend already
has an orange "pending" task badge. Add `PENDING` to the glossary in `AGENTS.md` and the backlog's errand states.

**2. A database and an outbox.** Errands and the outbox need tables, so add an `order-db` and an `order-migrate`
step to `compose.yaml`, copied from the supplier service. Then copy the outbox from `user-service` (`tables.py`
`outbox`, `outbox.py`, and its migration). Insert the command in the **same transaction** as the errand change. Publish to exchange `credit.commands` with the routing key
from the table below, `type` = command name, and `user_id = "order-service"` (RabbitMQ refuses anything else).

**3. A `credit_status` column** on errands, and these steps:

| Errand event | In the same transaction | Command | When the reply arrives |
|---|---|---|---|
| Created | `PENDING`, `credit_status = RESERVING` | `ReserveCredits {errandId, requesterId, amount}` | `HELD` → `OPEN`. `REJECTED` → end it and show `reason` (`INSUFFICIENT_CREDITS`, `NO_WALLET`) |
| Reward changed while `OPEN` (F7.3.1) | `reward_revision += 1` | `AdjustReservation {errandId, requesterId, amount, revision}` | reply `amount == new reward` → keep it; otherwise keep the old reward and say there aren't enough credits |
| Cancelled or expired, before completion | `CANCELLED`/`EXPIRED`, `credit_status = RELEASING` | `ReleaseCredits {errandId, requesterId, reason}` | `RELEASED` (or `REJECTED`: nothing was held) → `RELEASED` |
| Completed (requester confirms, or automatically after 1 hour) | `COMPLETED`, `credit_status = TRANSFERRING` | `TransferCredits {errandId, requesterId, courierId}` | `TRANSFERRED` → `TRANSFERRED`. `NO_COURIER_WALLET` → leave it and retry later |
| Accepted, picked up, delivered | — | none: credits don't move | — |

**4. A reply consumer** on queue `order-service.credit-replies` (it already exists, so replies sent while the Order
Service is down are kept). Check `message.user_id == "credit-service"` and `type == "ReservationResult"`, find the errand by
`errandId`, and apply the result only if it moves the errand forward. Replies can arrive twice; applying the same
result twice must change nothing. `correlation_id` is the command's `message_id`, if you want to log the pair.

**5. A reconciler** (e.g. every minute): errands whose `credit_status` has been `RESERVING`, `TRANSFERRING` or
`RELEASING` for more than 2 minutes get the same command again. That's safe because every command is idempotent.

**6. Pending on the wallet banner.** Return `creditStatus` with errands. On pages that show the banner, pass
`<CreditBanner pending={...} />` true when any of the user's errands (as requester or courier) is `TRANSFERRING` or
`RELEASING`. The banner then shows **Pending** and checks every 2 seconds until the change lands.

**7. Local credentials.** The `order-service` RabbitMQ login and its permissions already exist. Add
`RABBITMQ_URL: amqp://order-service:${RABBITMQ_ORDER_SERVICE_PASSWORD:?set RABBITMQ_ORDER_SERVICE_PASSWORD in .env}@rabbitmq:5672/`
to the `order-service` container in `compose.yaml` once it sends messages.

---

## 8. Demo script

Start with `docker compose up --build`, and open the RabbitMQ management UI (http://localhost:15672) in a second tab
to show queues filling and draining.

1. **Registration → allocation.** Register in the web app (http://localhost:8080). Explore shows the banner with
   **Pending**, then 100 Active / 0 Reserved. Or: `docker compose run --rm credit-demo register`.
   Say: one transaction with the outbox, published within a second, opened once by the worker.
2. **Reserve, transfer, release, before and after.** `docker compose run --rm credit-demo scenario <requester> <courier> --pause`
   (ids from step 1). Press Enter between steps; point out the repeated reserve and transfer changing nothing.
3. **Concurrency.** `docker compose run --rm credit-demo race <id> --count 50 --amount 7` on a fresh 100-credit user: 14 held,
   the rest refused, never negative.
4. **Credit service down while an errand completes (drill A).**
   ```
   docker compose stop credit-worker
   docker compose run --rm credit-demo reserve  --errand 900 --requester <r> --amount 10 --no-wait
   docker compose run --rm credit-demo transfer --errand 900 --requester <r> --courier <c> --no-wait
   ```
   Show `credit-service.commands` holding 2 messages and unchanged balances (`credit-demo balances <r> <c>`).
   `docker compose start credit-worker`: both apply, the courier is paid once.
5. **Broker down during registration (drill B).** `docker compose stop rabbitmq`, register a user (succeeds; banner
   Pending; `outbox` row unpublished with `last_error`), `docker compose start rabbitmq`: the wallet opens.
6. **Bad messages.** Show `credit-service.commands.dead`, and a worker log line such as
   `Dead-lettering ... TransferCredits may not be sent by 'user-service'`.
7. **Audit.** `docker compose run --rm credit-demo audit`: allocated = in circulation.
8. **Data survives (drill C).** `docker compose down` then `docker compose up`: balances unchanged.

## 9. Known limits and next steps

- **The Order Service doesn't create errands yet** (it only does AI autofill), so `credit-demo` plays its part in the
  credit flow. Section 7 is what it needs to do.
- **The settlement "pending" pill** depends on the Order Service reporting `creditStatus`; the wallet-opening pending
  state works now.
- **Email verification (F1.1.5)** isn't enforced by the User Service yet; the wallet opens at registration either way.
- **Local AMQP is unencrypted** inside the Compose network; deployed environments should use `amqps://` (N8.1.1).
- **Single RabbitMQ node** locally. Quorum queues replicate across nodes once a cluster is used in the cloud.
- **Long database outages:** RabbitMQ closes a consumer that holds a message for over 30 minutes (its default
  consumer timeout). The message is redelivered, and after 5 such redeliveries it's dead-lettered, to be moved back
  once the database is fixed.
- **`postgres:18`** is pinned by major version only (see 6.2).
