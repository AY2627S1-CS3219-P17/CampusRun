<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
Scope: AI-drafted plan for the admin dashboard, from the team's chosen scope (all errands view, predefined delivery
       locations, promoting users, giving up your own admin role).
Author review: <to be completed by author>
-->

# Admin Dashboard Plan

Last updated: 2026-11-09 (approved; Tasks 1 and 2 done)

> **How this plan is carried out:** one task at a time. **After every task, stop for a manual review.** Write the
> detailed code for a task only when that task starts.

**Goal:** a simple admin page, `/admin`, covering the admin-only actions that have no UI yet. Supplier create, edit
and deactivate are already done on the Suppliers page and stay there.

**Scope (chosen by the team):**

| Area | Backend | Frontend |
|---|---|---|
| All errands | Done: `GET /api/orders/admin/errands` | New |
| Predefined delivery locations | Done: `POST`/`PATCH /api/orders/delivery-locations` with `predefined` | New |
| Promote a student to admin | **New** in user-service | New |
| Give up your own admin role, if another admin is left | **New** in user-service | New |

Out of scope: `GET /admin/stuck`, `GET /api/credits/admin/audit`, demoting *other* admins, deactivating users.

## Decisions

| # | Decision | Why |
|---|---|---|
| A1 | Admins can be created through the API, not just by the `create-initial-admin` script | Replaces "promotion is deferred" in `admin-role-plan.md`. The seed script stays for the first admin. |
| A2 | An admin can only demote themselves, and only while at least one other admin exists | There's always an admin, and no admin can lock out another. |
| A3 | Role changes are serialized with a Postgres transaction-level advisory lock (`pg_advisory_xact_lock`) | With two admins giving up at the same moment, a count-then-update would pass for both and leave none. Role changes are rare, so one at a time costs nothing. |
| A4 | Both role endpoints re-check the caller's role in the database, inside the lock | The role is read from the access token. An admin who just gave up still holds an admin token for up to 5 minutes, and could otherwise use it to promote themselves straight back. |
| A5 | No sessions end on a role change | `/auth/refresh` already re-reads the role (`sessions.py`), so the new role reaches the next access token within `JWT_ACCESS_TOKEN_TTL_SECONDS` (5 min). The frontend refreshes at once after a give-up. |
| A6 | The user list returns id, username, email and role only | Emails are personal data, and admins need them to find the right account. Nothing else is exposed, and emails aren't logged. |
| A7 | Role changes are logged as actor id → target id | `admin-role-plan.md` says admin actions are logged. |

## API (user-service, new)

All three need `CurrentAdmin`. They're not under `/internal/`, which the gateway blocks. JSON is snake_case, like
the rest of user-service.

- **`GET /admin/users?q=&role=&page=&page_size=`:** search by username or email (case-insensitive substring).
  `role` is `student` or `admin`. Returns `{items: [{id, username, email, role}], total, page, page_size,
  total_pages}`, ordered by username.
- **`POST /admin/users/{user_id}/promote`:** 200 with the user. 404 if unknown, 409 if already an admin, 403 if the
  caller is no longer an admin in the database (A4).
- **`POST /admin/me/step-down`:** 200 with the caller's updated user. 409 if they're the only admin left, 403 if
  they're no longer an admin (A4).

## Tasks

### Task 1: user-service role endpoints

- **Files:** `main.py` (or a new `admin.py` router), `schemas.py`, a new `tests/test_admin.py`.
- **Tests:**
  - A student gets 403 on all three.
  - Search by username and by email, and filter by role.
  - Promote: success, 404, and 409 when already an admin.
  - Step down: works with two admins, and is refused (409) for the last one.
  - A stale admin token, after stepping down, can't promote anyone (403).
  - After a refresh, the token carries the new role.
- **Docs:**
  - `user-service/README.md`.
  - The contradicted lines in `admin-role-plan.md`, `user-service-setup-plan.md` and `auth-plan.md`.
  - The README AI summary.

### Task 2: frontend `/admin` shell and Users tab

- **Routing and navigation:**
  - An `AdminRoute` guard in `main.tsx` sends students to `/explore`.
  - Only admins see the Admin link in `header.tsx`.
  - The page has three tabs: Errands, Delivery locations and Users.
- **Users tab:**
  - Search, a role filter, pages, and Promote (with a confirmation).
  - "Step down as admin" on your own row, hidden if you're the only admin. The server still makes the real check.
  - After stepping down, refresh the token and go to `/explore`.
- **API:** new functions in `api/user.ts`.

### Task 3: frontend Errands tab

- **List:** all errands, with search, a state filter, sorting and pages.
- **Read-only:** no errand actions (D1 in the order-service plan). Check `ErrandList`/`toTaskCard` and add an
  `admin` viewer that shows both requester and courier with no action buttons.
- **From the Users tab:** "View errands" on a user opens this tab filtered by `requesterId` or `courierId`.

### Task 4: frontend Delivery locations tab

- **List:** predefined locations, with search and an Active / Deactivated toggle (`active=false` lists the
  deactivated ones).
- **Form:** create and edit name, floor, description and a map position, using `interactive-map`. Deactivate and
  reactivate from the same form.
- **Errors shown in the form:**
  - 409: a courier is on the way, or the name is a duplicate.
  - 422: the position is outside the served area.

## Checks

- `mise run test` in `user-service/`.
- `npm run build` (type-check and build) in `frontend/`.
- Manual check of each task in the browser, from the checklist given after it.
