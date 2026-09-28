<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-28
Scope: AI-generated plan for replacing the separate admins table with a role on users, based on the team's decisions;
       AI-revised it so admins keep every student capability (2026-09-28).
Author review: <to be completed by author>
-->

# Admin Role Plan

Last updated: 2026-09-28

**Status:** implemented on branch `change-admin-design` (revision `cb86242157bd`). The "Other services" notes are still to do when those services get auth.

> **Revised 2026-09-28: admins keep every student capability.** The team first made admins admin-only (no errands, no credit account). Because every account must use a unique `@u.nus.edu` email, a promoted student couldn't keep a second account, so promotion would have locked them out of errands. Admin is now extra permissions on top of a student account. `require_student` and `CurrentStudent` were removed, and the frontend shows the errand pages to everyone. Items below that say admins are kept out of errands are superseded by this note and kept as history.

Admins stop being separate accounts in their own `admins` table. They become rows in `users` with `role = 'admin'`, and they sign in through the same `/auth/login` and login page as students. Protected operations check the token's `role` claim, not `type`.

## Decisions

- **The token claim `type` becomes `role`,** with values `"student" | "admin"`. Every service rejects tokens that carry only `type`. Ship all three sections below in one PR, because the rename breaks older services.
- **Add a new migration.** Teammates have already applied `717eccffe95a`, so don't edit it. Rows in `admins` are dropped, not moved over: they have no email.
- ~~**Admins are admin-only.** They have no credit account and can't post or accept errands.~~ **Superseded:** admins keep every student capability: they can post and accept errands and have a credit account. Admin powers can't be used on errands or credits involving the admin themselves, and admin actions are logged.
- **Registration accepts `@u.nus.edu` only,** and `@nus.edu.sg` staff addresses are no longer allowed. Registration always creates a `student`.
- **Admins are created only by the `create-initial-admin` script.** Admins also use an `@u.nus.edu` email, checked by the same rule as registration. No API sets `role`, and promotion is deferred.
- **Trade-off:** a demoted admin keeps admin access until their current token expires, up to `JWT_ACCESS_TOKEN_TTL`.

## user-service

1. **`tables.py`:**
   - Remove `admins` and `uq_admins_username_lower`.
   - Add `role` to `users`: `String(16)`, not null, `server_default="student"`.
   - Add a CHECK constraint `role IN ('student', 'admin')`, named via the naming convention.
2. **Migration:** autogenerate a new revision (e.g. `add_role_to_users_drop_admins`) and review it.
   - Upgrade adds the column with its default and the CHECK constraint, then drops `admins` and its index.
   - Downgrade reverses both. Admin rows aren't restored.
   - `test_migrations` should keep passing (tables and migrations match).
3. **`security.py`:**
   - Rename `AccountType` to `Role`.
   - `create_access_token(account_id, role, settings)` writes `"role"`.
   - `decode_access_token` requires `["sub", "role", "exp"]`.
4. **`auth.py`:**
   - Remove `admin_scheme`, so Swagger only offers `UserAuth`.
   - `Account(id, role)`.
   - Add three dependencies:
     - `require_user`: any role, since an admin is a user too. Used for `/users/me`.
     - `require_student`: for student-only routes, and the pattern other services copy.
     - `require_admin`.
   - Export `CurrentUser` (any role), `CurrentStudent` and `CurrentAdmin`.
5. **`main.py`:**
   - Delete `/auth/admin/login` and `/admins/me`.
   - `/auth/login` also selects `users.c.role` and passes it to `create_access_token`.
   - `GET` and `PATCH /users/me` keep `CurrentUser`, which now accepts admins, and return `role`.
   - `/auth/register` inserts without `role`, so the database default applies.
6. **`schemas.py`:**
   - Delete `AdminResponse` and add `role` to `UserResponse`.
   - Set `ALLOWED_EMAIL_DOMAINS = {"u.nus.edu"}` and update the error message and comment.
   - Give `RegisterRequest` `extra="forbid"`, so `role` can't be sent.
7. **`scripts/create_admin.py`:**
   - Add `INITIAL_ADMIN_EMAIL` to `Settings`, next to the username and password.
   - Validate the email, username and password with the same rules as registration (`@u.nus.edu` only), e.g. by building a `RegisterRequest`.
   - Skip if any user has `role = 'admin'`.
   - Insert into `users` with `role='admin'`. Keep the concurrency guard.
   - If the email or username is already taken by a student, fail with a clear message.
8. **Config:** add `INITIAL_ADMIN_EMAIL=` to `user-service/.env.example`. Update the `create-admin` task description in `mise.toml`.
9. **Tests:**
   - `test_auth.py`:
     - An admin logs in through `/auth/login`, and the token has `role: "admin"`.
     - `/users/me` works for both roles and returns `role`.
     - A `require_student` route returns 403 for an admin (add a test-only route, or wait for the first real one).
     - A token with `type` but no `role` gets 401.
     - Remove the separate-table and shared-id tests.
   - `test_register.py`:
     - Flip `test_accepts_staff_email` to expect 422.
     - Sending `role: "admin"` gets 422.
     - A new account's token has `role: "student"`.
   - `test_update_user.py`: replace `test_rejects_admin_token` with "admin can update their own profile".
   - `test_create_admin.py`: rewrite against `users`. Cover the email being required, a non-`@u.nus.edu` email being rejected, skipping when an admin exists, and the email or username already being taken by a student.

## supplier-service

1. **`auth.py`:**
   - Read `claims.get("role")` and add `"role"` to `require`.
   - Update the module docstring and header.
   - `Role`, `AnyUser` and `AdminUser` are otherwise unchanged. Supplier reads stay open to both roles.
2. **`scripts/make_token.py`:** `--type` becomes `--role`, and the `"role"` claim is written.
3. **Tests:**
   - `conftest.make_token` emits `role`.
   - In `test_auth.py`, the "old claim name" case becomes a token with only `type`, which gets 401.
4. **No data change:** `created_by` and `updated_by` now hold real `users.id` values. Before, admin ids overlapped with student ids.

## frontend

1. **`utils/session.ts`:** read `claims.role` instead of `claims.type`, and update the comment.
2. **`types/user.ts`:** add `role: 'student' | 'admin'` to `User`.
3. **Admin navigation:** admins can't take part in errands, so:
   - Hide My Tasks and My Requests in `header.tsx` for admins. Explore stays visible to everyone.
   - Guard `/my-tasks` and `/my-requests` in `main.tsx`: an admin is redirected to `/explore`.
   - Login keeps sending everyone to the same landing page.
   - Once errand actions exist on Explore (posting or accepting), hide them for admins. The order-service 403 stays the real check.
4. **No login changes:** the login page is already shared. Admin controls already check `session.role` (`pages/suppliers.tsx:70`). `utils/validation.ts` already requires `@u.nus.edu`.

## Other services (notes only, no code yet)

- **order-service:** errand routes use `require_user`, so both roles can post and accept errands. Any future admin action on errands (e.g. dispute resolution, forced cancellation) is refused when the admin is the requester or courier.
- **credit-service:** every user needs a credit account. `/auth/register` publishes `user.registered`, and `create-initial-admin` must publish it too, so the seeded admin gets an account. Any future admin credit adjustment is refused on the admin's own account.
- Update the "Adding auth to another service" steps in `docs/auth-plan.md` to match.

## Docs and READMEs

- **`README.md` (root):**
  - AI Use Summary: add a bullet for this change.
  - Keep the "Decisions made by the team" line and the separate-admin bullets as history, and note that the team later replaced them.
- **`user-service/README.md`:**
  - Service description: "admin accounts" becomes "admin role".
  - "Creating the initial admin": add `INITIAL_ADMIN_EMAIL` to both the mise and Docker commands, and change "empty `admins` table" to "no user with the admin role".
  - "Protecting an endpoint": `CurrentUser` now accepts any role, plus the new `CurrentStudent` and the existing `CurrentAdmin`, with `Account(id, role)` and the 403 example.
- **`supplier-service/README.md`:** the token section describes `role` (`student` or `admin`), and `make_token.py --role`. Change "account type isn't allowed" to "role isn't allowed".
- **`docs/user-service-setup-plan.md`:** update the step 3 `admins` bullet and the two "Decisions" bullets about separate admin accounts.
- **`docs/auth-plan.md`:**
  - Update the design summary's claims row.
  - Update steps 2.3–2.8: one scheme, one login, no `AdminResponse`, and the tests.
  - Part 3: seed the admin with an email, then log in through the normal form.
  - Update the future notes.
- **`ai/usage-log.md`:** only if you ask.
- **AI disclosure headers:** update them on every file this touches.

## Checks

- **Tests:** run `mise run test` in `user-service/` and `supplier-service/`.
- **Migration:** run `docker compose up --build`. `user-migrate` applies the new revision on top of the existing one without errors.
- **Seed an admin:** set `INITIAL_ADMIN_*` in the root `.env`, run `docker compose up`, then check `docker compose logs user-seed-admin`.
- **As the admin in the web app:**
  - Log in on the normal login page.
  - Explore is visible, and Suppliers shows the create and edit controls.
  - My Tasks and My Requests are hidden, and visiting `/my-tasks` redirects to `/explore`.
- **As a student:** registering with `@nus.edu.sg` is rejected. A new `@u.nus.edu` account sees all three tabs and no supplier admin controls.
