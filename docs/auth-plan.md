<!--
AI Assistance Disclosure:
Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-26
Scope: AI-generated step-by-step guide for the nginx gateway and JWT authentication in the user service,
       based on design decisions discussed with the team.
Author review: <to be completed by author>
-->

# Gateway + Auth Implementation Guide

This guide walks through adding an **nginx gateway** in front of the services and **password login with JWT access tokens** in `user-service`. It follows FastAPI's [Security tutorial](https://fastapi.tiangolo.com/tutorial/security/first-steps/), adapted for our setup (async SQLAlchemy Core, separate `users`/`admins` tables, multiple services).

Work through the parts in order. Each step ends with a **Check** so you know it worked before moving on.

## Contents

- [Design summary](#design-summary)
- [Part 1: Gateway](#part-1-gateway)
- [Part 2: Auth in user-service](#part-2-auth-in-user-service)
- [Part 3: Try it end to end](#part-3-try-it-end-to-end)
- [Future notes](#future-notes)

---

## Design summary

```
                    ┌──────────── Compose network (private) ────────────┐
browser ──:8080──►  gateway (nginx) ──/api/users/*──►  user-service ──► user-db
                    │                ──/api/suppliers/*► supplier-service (later)
                    │                ──/api/orders/*──►  order-service   (later)
                    └────────────────────────────────────────────────────┘
```

| Decision | Choice | Why |
| --- | --- | --- |
| Entry point | One nginx container; the only service with a published port | The frontend uses one origin, so no CORS setup. The services stay unreachable from outside. |
| Credential | JWT access token in `Authorization: Bearer <token>` | Any service can verify it locally with no call to user-service. |
| Signing | HS256 with a shared `JWT_SECRET` | Simplest option. Trade-off: every service holding the secret could also mint tokens. That's acceptable for this project. |
| Token claims | `sub` (account id, as a string), `type` (`"user"` or `"admin"`), `iat`, `exp` | `users` and `admins` are separate tables and **both have ids starting at 1**. Without `type`, admin #1 and user #1 look the same. |
| Lifetime | 60 minutes, no refresh tokens | Keeps the scope small. Logout = the frontend discards the token. |
| Login input | `OAuth2PasswordRequestForm` (form-encoded `username` + `password`) | Makes Swagger's **Authorize** button work. The `username` field accepts **email or username**. |
| Requester/courier toggle | Frontend UI mode only; not stored and not in the token | Every user can do both. Order-service enforces rules per errand, e.g. "can't accept your own". |

---

## Part 1: Gateway

### Step 1.1: Write the nginx config

Create `gateway/nginx.conf`:

```nginx
# AI Assistance Disclosure: (add header as per AGENTS.md)

server {
    listen 80;

    # Pass the original client details on to the services
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # The trailing slashes strip the prefix: /api/users/auth/login reaches user-service as /auth/login
    location /api/users/ {
        proxy_pass http://user-service:8000/;
    }

    # Nothing else is routed yet (the frontend will go here later)
    location / {
        return 404;
    }
}
```

`user-service` is the Compose service name. Docker's internal DNS resolves it to the container.

### Step 1.2: Tell FastAPI it lives under `/api/users`

The gateway strips `/api/users` before forwarding, so user-service receives `/docs`. The Swagger page it returns would then request `/openapi.json` from the browser, which the gateway doesn't route. FastAPI's `root_path` fixes this: routes still match `/docs`, `/auth/login` and so on, but generated URLs (the OpenAPI schema and the "Try it out" requests) get the `/api/users` prefix.

Make it a setting, so running the service directly on your machine (no gateway) still works.

In `user-service/src/user_service/config.py`, add to `Settings`:

```python
    # Path prefix the gateway serves this service under, e.g. "/api/users"; empty when accessed directly
    root_path: str = ""
```

In `user-service/src/user_service/main.py`, pass it to the app:

```python
app = FastAPI(
    title="CampusRun User Service",
    lifespan=lifespan,
    root_path=settings.root_path,
    # ...docs_url / redoc_url / openapi_url unchanged
)
```

### Step 1.3: Add the gateway to Compose and un-publish user-service

In `compose.yaml`:

1. **Remove** the `ports:` block from `user-service`. The gateway is now the only way in. Keep `user-db`'s `127.0.0.1:5433` port, since mise and Alembic on your host use it.
2. Add `ROOT_PATH` to `user-service`'s environment:
   ```yaml
   user-service:
     build: ./user-service
     environment:
       DATABASE_URL: ...        # unchanged
       ENABLE_DOCS: "true"      # unchanged
       # Must match the gateway's location prefix for this service
       ROOT_PATH: /api/users
     depends_on: ...            # unchanged
   ```
3. Add the gateway service:
   ```yaml
   # Public entry point: routes /api/<service>/... to each service on the private network
   gateway:
     image: nginx:stable-alpine
     volumes:
       - ./gateway/nginx.conf:/etc/nginx/conf.d/default.conf:ro
     ports:
       - "8080:80"
     depends_on:
       - user-service
   ```

**Check**

```sh
docker compose up --build -d
curl -i http://localhost:8080/api/users/health   # → 200 {"status":"ok","database":"ok"}
curl -i http://localhost:8001/health             # → connection refused (no longer published)
```

Open <http://localhost:8080/api/users/docs>. The Swagger page should load, and **Try it out** on `/health` should succeed.

> **Troubleshooting: 502 Bad Gateway after recreating a service.** nginx looks up `user-service`'s IP once at startup. If the container is recreated with a new IP, run `docker compose restart gateway`.

---

## Part 2: Auth in user-service

All commands in this part run from `user-service/`.

### Step 2.1: Add PyJWT

```sh
uv add pyjwt
```

`python-multipart`, which `OAuth2PasswordRequestForm` needs, is already included in `fastapi[standard-no-fastapi-cloud-cli]`.

### Step 2.2: JWT settings

1. **Generate a secret.** HS256 needs at least 32 bytes; PyJWT warns about shorter keys:
   ```sh
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. **Root `.env.example`:** it already has `JWT_SECRET` and `JWT_ACCESS_TOKEN_TTL`. Add a comment that the TTL is in **minutes**. `JWT_REFRESH_TOKEN_TTL` stays unused for now (see [Future notes](#future-notes)). Put the real secret in your root `.env`.
3. **`user-service/.env.example`:** add `JWT_SECRET=` too, so `mise run serve` and `mise run create-admin` work on your host. Put the same value in `user-service/.env`.
4. **`compose.yaml`:** pass both to `user-service`:
   ```yaml
       JWT_SECRET: ${JWT_SECRET:?set JWT_SECRET in .env}
       JWT_ACCESS_TOKEN_TTL: ${JWT_ACCESS_TOKEN_TTL:-60}
   ```
   Also add the `JWT_SECRET` line to **`user-migrate`**. `migrations/env.py` loads the app `Settings` to read `DATABASE_URL`, so without the secret the migrate container fails validation, and `user-service` never starts because it waits for migrations to finish.
5. **`config.py`:** add to `Settings` (import `Field` from `pydantic`):
   ```python
       # Signs and verifies access tokens; at least 32 characters so HS256 isn't brute-forceable
       jwt_secret: SecretStr = Field(min_length=32)
       # Minutes an access token stays valid
       jwt_access_token_ttl: int = 60
   ```

`jwt_secret` has no default on purpose, so the service refuses to start without one. **Anything that loads `Settings` now needs the secret:** the server, Alembic (`user-migrate` and `mise run migrate`) and the `create-initial-admin` script. Steps 3 and 4 above cover all of them.

**Check:** `uv run python -c "from user_service.config import get_settings; print(get_settings().jwt_access_token_ttl)"` prints `60` (run with `JWT_SECRET` set in `user-service/.env`).

### Step 2.3: Token helpers in `security.py`

Add these to `user-service/src/user_service/security.py`. They correspond to the "create_access_token" part of the tutorial's [JWT page](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).

```python
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from user_service.config import Settings

ALGORITHM = "HS256"

AccountType = Literal["user", "admin"]

# Verified against when the account doesn't exist, so a failed login takes the same time either way
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


def create_access_token(account_id: int, account_type: AccountType, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        # PyJWT requires "sub" to be a string
        "sub": str(account_id),
        "type": account_type,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_ttl),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    # Raises jwt.InvalidTokenError (bad signature, expired, malformed, missing claims)
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        # Pinning the algorithm stops a forged token from choosing "none"
        algorithms=[ALGORITHM],
        options={"require": ["sub", "type", "exp"]},
    )
```

### Step 2.4: Response schemas

Add to `schemas.py` (and add `from typing import Literal` to its imports):

```python
class TokenResponse(BaseModel):
    # Field names are fixed by the OAuth2 spec; Swagger's Authorize button reads them
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class AdminResponse(BaseModel):
    id: int
    username: str
    created_at: datetime
```

### Step 2.5: Auth dependencies in a new `auth.py`

This corresponds to the tutorial's [Get Current User](https://fastapi.tiangolo.com/tutorial/security/get-current-user/) page, with one difference: the dependency returns what the **token** says (id and type) and doesn't load the user from the database. Other services will use the same approach later, since they can't access the user DB.

Create `user-service/src/user_service/auth.py`:

```python
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from user_service.config import Settings, get_settings
from user_service.security import AccountType, decode_access_token

# Two schemes so Swagger's Authorize dialog offers both logins; both read the same Bearer header.
# scheme_name must differ, or the two collide in the OpenAPI schema.
# tokenUrl only tells Swagger where to log in; prefixing root_path makes it right both directly and behind the gateway
user_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().root_path}/auth/login", scheme_name="UserAuth"
)
admin_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().root_path}/auth/admin/login", scheme_name="AdminAuth"
)


@dataclass(frozen=True)
class Account:
    id: int
    type: AccountType


def credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _account_from_token(token: str, settings: Settings) -> Account:
    try:
        payload = decode_access_token(token, settings)
    except jwt.InvalidTokenError:
        raise credentials_error() from None
    return Account(id=int(payload["sub"]), type=payload["type"])


def _require(account: Account, expected: AccountType) -> Account:
    # Valid token, wrong kind of account: authenticated but not allowed
    if account.type != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


async def require_user(
    token: Annotated[str, Depends(user_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Account:
    return _require(_account_from_token(token, settings), "user")


async def require_admin(
    token: Annotated[str, Depends(admin_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Account:
    return _require(_account_from_token(token, settings), "admin")


CurrentUser = Annotated[Account, Depends(require_user)]
CurrentAdmin = Annotated[Account, Depends(require_admin)]
```

**401 vs 403:** a missing, invalid or expired token gets **401** ("who are you?"). A valid token for the wrong account type gets **403** ("I know who you are, and you can't do this"). `OAuth2PasswordBearer` already returns 401 when the header is missing.

### Step 2.6: Login endpoints

This corresponds to the tutorial's [Simple OAuth2](https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/) and [JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) pages.

Add to `main.py`. You'll need new imports: `OAuth2PasswordRequestForm` from `fastapi.security`; `func`, `or_` and `select` from `sqlalchemy`; `admins` from `tables`; and the new schemas, `security` helpers and `auth` items.

```python
SettingsDep = Annotated[Settings, Depends(get_settings)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


def login_failed() -> HTTPException:
    # One message for unknown account and wrong password, so it doesn't reveal which accounts exist
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect login or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def check_password(password: str, stored_hash: str | None) -> bool:
    # The form doesn't enforce RegisterRequest's limit, so cap the hashing work here too
    if len(password) > PASSWORD_MAX_LENGTH:
        return False
    # Always run one Argon2 verify, even for unknown accounts, so timing doesn't reveal them
    return await run_in_threadpool(password_hash.verify, password, stored_hash or DUMMY_HASH)


@app.post("/auth/login")
async def login(form: LoginForm, conn: Connection, settings: SettingsDep) -> TokenResponse:
    # Usernames can't contain "@", so an email and a username never match the same input
    identifier = form.username.strip().lower()
    row = (
        await conn.execute(
            select(users.c.id, users.c.password_hash).where(
                or_(func.lower(users.c.email) == identifier, func.lower(users.c.username) == identifier)
            )
        )
    ).one_or_none()

    # Check the password before testing row, so unknown accounts still pay for a hash
    valid = await check_password(form.password, row.password_hash if row else None)
    if row is None or not valid:
        raise login_failed()
    return TokenResponse(access_token=create_access_token(row.id, "user", settings))


@app.post("/auth/admin/login")
async def admin_login(form: LoginForm, conn: Connection, settings: SettingsDep) -> TokenResponse:
    row = (
        await conn.execute(
            select(admins.c.id, admins.c.password_hash).where(
                func.lower(admins.c.username) == form.username.strip().lower()
            )
        )
    ).one_or_none()

    # Check the password before testing row, so unknown accounts still pay for a hash
    valid = await check_password(form.password, row.password_hash if row else None)
    if row is None or not valid:
        raise login_failed()
    return TokenResponse(access_token=create_access_token(row.id, "admin", settings))
```

The `func.lower(...) == ...` comparisons match the case-insensitive unique indexes in `tables.py`, so Postgres can use them.

### Step 2.7: Your first protected routes

Add to `main.py`:

```python
@app.get("/users/me")
async def read_current_user(account: CurrentUser, conn: Connection) -> UserResponse:
    row = (
        await conn.execute(
            select(
                users.c.id,
                users.c.email,
                users.c.username,
                users.c.email_verified_at,
                users.c.created_at,
            ).where(users.c.id == account.id)
        )
    ).one_or_none()
    # The token can outlive the account, e.g. if the user was deleted after logging in
    if row is None:
        raise credentials_error()
    return UserResponse.model_validate(row, from_attributes=True)


@app.get("/admins/me")
async def read_current_admin(account: CurrentAdmin, conn: Connection) -> AdminResponse:
    row = (
        await conn.execute(
            select(admins.c.id, admins.c.username, admins.c.created_at).where(admins.c.id == account.id)
        )
    ).one_or_none()
    if row is None:
        raise credentials_error()
    return AdminResponse.model_validate(row, from_attributes=True)
```

To protect any future route, add a `CurrentUser` or `CurrentAdmin` parameter. That's the whole pattern.

### Step 2.8: Tests

**`tests/conftest.py`:** next to the existing `DATABASE_URL` default, add a test secret so `Settings` can load:

```python
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters-long")
```

This also covers `test_create_admin.py`, because `Settings(_env_file=None, ...)` still reads real environment variables.

**`tests/test_auth.py`:** a starting point in the same style as `test_register.py`:

```python
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import get_settings
from user_service.security import ALGORITHM, password_hash
from user_service.tables import admins

pytestmark = pytest.mark.anyio

USER = {"email": "alice@u.nus.edu", "username": "alice", "password": "s3cret-pass"}
ADMIN = {"username": "root", "password": "admin-pass"}


@pytest.fixture
async def user(client: AsyncClient) -> dict:
    response = await client.post("/auth/register", json=USER)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
async def admin(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            insert(admins).values(
                username=ADMIN["username"], password_hash=password_hash.hash(ADMIN["password"])
            )
        )


async def login(client: AsyncClient, username: str, password: str, path: str = "/auth/login"):
    # data= sends a form body, which OAuth2PasswordRequestForm expects
    return await client.post(path, data={"username": username, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_token(secret: str | None = None, **overrides) -> str:
    claims = {"sub": "1", "type": "user", "exp": datetime.now(UTC) + timedelta(minutes=5), **overrides}
    # exp=None means "leave the claim out"
    claims = {key: value for key, value in claims.items() if value is not None}
    return jwt.encode(claims, secret or get_settings().jwt_secret.get_secret_value(), algorithm=ALGORITHM)


@pytest.mark.parametrize("identifier", ["alice@u.nus.edu", "ALICE@U.NUS.EDU", "alice", "Alice", "  alice  "])
async def test_login_accepts_email_or_username(client: AsyncClient, user: dict, identifier: str) -> None:
    response = await login(client, identifier, USER["password"])

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["sub"] == str(user["id"])
    assert claims["type"] == "user"


@pytest.mark.parametrize(
    ("identifier", "password"),
    [("alice", "wrong-password"), ("nobody", USER["password"]), ("alice", "x" * 10_000)],
)
async def test_login_failures_look_identical(
    client: AsyncClient, user: dict, identifier: str, password: str
) -> None:
    response = await login(client, identifier, password)

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect login or password"


async def test_me_returns_current_user(client: AsyncClient, user: dict) -> None:
    token = (await login(client, "alice", USER["password"])).json()["access_token"]

    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        make_token(exp=datetime.now(UTC) - timedelta(minutes=1)),  # expired
        make_token(secret="some-other-secret-that-is-32-chars-long!"),  # forged
        make_token(exp=None),  # no expiry
    ],
)
async def test_me_rejects_invalid_tokens(client: AsyncClient, user: dict, token: str) -> None:
    response = await client.get("/users/me", headers=bearer(token))

    assert response.status_code == 401


async def test_admin_login_and_me(client: AsyncClient, admin: None) -> None:
    token = (await login(client, "root", ADMIN["password"], "/auth/admin/login")).json()["access_token"]

    response = await client.get("/admins/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "root"


async def test_tokens_only_work_for_their_account_type(
    client: AsyncClient, user: dict, admin: None
) -> None:
    user_token = (await login(client, "alice", USER["password"])).json()["access_token"]
    admin_token = (await login(client, "root", ADMIN["password"], "/auth/admin/login")).json()["access_token"]

    # Both accounts have id 1, so only the "type" claim tells them apart
    assert (await client.get("/admins/me", headers=bearer(user_token))).status_code == 403
    assert (await client.get("/users/me", headers=bearer(admin_token))).status_code == 403


async def test_user_login_rejects_admin_credentials(client: AsyncClient, admin: None) -> None:
    response = await login(client, "root", ADMIN["password"])

    assert response.status_code == 401
```

> `make_token(...)` in the `parametrize` list runs when the module is imported, so `JWT_SECRET` must already be set. The `os.environ.setdefault` in `conftest.py` handles that, because pytest imports `conftest.py` first.

**Check:** `mise run test` passes, including the existing registration and admin tests.

---

## Part 3: Try it end to end

```sh
docker compose up --build -d
```

**In Swagger** at <http://localhost:8080/api/users/docs>:

1. `POST /auth/register` with an NUS email.
2. Click **Authorize** and use the **UserAuth** form: enter your email or username plus your password, and leave client_id/secret empty.
3. `GET /users/me` should return your profile. Log out in the Authorize dialog and it should return 401.
4. Seed an admin with `mise run create-admin` (from `user-service/`, using `INITIAL_ADMIN_*` in `user-service/.env`), or in Docker:
   ```sh
   docker compose run --rm -e INITIAL_ADMIN_USERNAME=root -e INITIAL_ADMIN_PASSWORD='admin-pass' user-service create-initial-admin
   ```
   Then log in via the **AdminAuth** form and call `GET /admins/me`.

**With curl:**

```sh
TOKEN=$(curl -s -X POST http://localhost:8080/api/users/auth/login \
  -d username=alice -d password='s3cret-pass' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -i http://localhost:8080/api/users/users/me -H "Authorization: Bearer $TOKEN"
```

(Yes, `/api/users/users/me` has "users" twice: the gateway prefix plus the route. If that bothers you, rename the route to `/me`.)

**Finally:** add the AI Assistance Disclosure headers to the files you changed (as per `AGENTS.md`), and add a bullet to the README's AI Use Summary.

---

## Future notes

These are for later milestones and other services. Not needed for D2.

### Adding auth to another service (supplier-, order-, credit-service)

1. **Gateway:** add a `location /api/<name>/ { proxy_pass http://<name>-service:8000/; }` block to `gateway/nginx.conf` and a `depends_on` entry to the gateway.
2. **Compose:** don't publish the service's port. Give it `ROOT_PATH: /api/<name>` and `JWT_SECRET: ${JWT_SECRET:?...}`.
3. **Code:** copy a trimmed `auth.py` into the service. Keep `Account`, `credentials_error`, `require_user`/`require_admin`, and the decode logic from `decode_access_token`. It needs only `pyjwt` and the secret; no database, no password hashing, no `create_access_token`. Keep `ALGORITHM` and the required claims identical to user-service's.
4. **`tokenUrl`** in other services must point at user-service's login through the gateway: `OAuth2PasswordBearer(tokenUrl="/api/users/auth/login", scheme_name="UserAuth")`. Swagger's Authorize button on those services only works through the gateway.
5. The user id is `int(account.id)`. Store it in that service's tables as a plain integer column (e.g. `requester_id`). There's no foreign key, because the users table lives in another database.

### Registration → credit account (M6 async)

- After inserting the user, user-service publishes a `user.registered` event with `{user_id}` to a broker (RabbitMQ or Redis Streams). Credit-service consumes it and creates the account with the initial credit allocation.
- Make the consumer idempotent (skip if an account for that `user_id` exists), because brokers can deliver twice.
- For the short gap before the event is processed, credit-service should create the account on first request, or return the initial balance, rather than 404.
- The client **never** creates credit accounts itself.
- For the demo, this is a good candidate to present as the M6 async workflow.

### Frontend

- **Login** sends **form data**, not JSON: `new URLSearchParams({ username, password })` with `Content-Type: application/x-www-form-urlencoded`. Label the field "Email or username".
- **Token storage:** keep the token in memory plus `sessionStorage`/`localStorage`, and attach it as `Authorization: Bearer ...` on every API call. On any 401, clear it and redirect to login.
- **Logout** = delete the stored token.
- **Requester/courier toggle** is a UI mode only, and nothing is sent to the backend.
- **Serving:** once built, serve the frontend from the gateway (`location / { root ...; try_files $uri /index.html; }`, replacing the `return 404`) so it's the same origin as the API.

### Nice-to-haves that build on this

- **User suspension (N1):** add a `suspended_at` column and reject suspended users in `/auth/login`. Existing tokens stay valid until they expire (≤60 min). If that's not acceptable, also check the column in user-service's protected routes, or add refresh tokens.
- **Login audit logs (N1):** record successes and failures in the login endpoints. To log the real client IP, start the service with `--forwarded-allow-ips` set to the gateway, so FastAPI trusts the gateway's `X-Forwarded-For`.
- **Refresh tokens:** `JWT_REFRESH_TOKEN_TTL` is already in `.env.example`. If you add them, store refresh tokens in the user DB so they can be revoked. Otherwise remove the variable to avoid confusion.
- **Email verification:** `users.email_verified_at` exists. Decide whether login (or only certain actions) requires a verified email.
- **Rehashing:** `password_hash.verify_and_update` can upgrade old hashes on login if pwdlib's recommended parameters change.

### Cloud deployment

- On Cloud Run, each service gets a public URL by default. To keep only the gateway public, set the other services' ingress to **internal** and point nginx's `proxy_pass` at their internal URLs, or use a managed API gateway instead of nginx.
- Store `JWT_SECRET` in a secret manager, not in plain environment config.
