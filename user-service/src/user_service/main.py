# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated FastAPI app with engine lifespan and GET /health endpoint; AI-updated lifespan return type to AsyncGenerator and made API docs depend on ENABLE_DOCS;
#        AI-completed the POST /auth/register endpoint from the author's draft; AI-renamed the user token type to "student" (Claude Code, 2026-09-27).
# Author review: reviewed by Nathan

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.auth import CurrentAdmin, CurrentUser, credentials_error
from user_service.auth import CurrentUser
from user_service.config import Settings, get_settings
from user_service.db import Connection, create_engine, get_engine
from user_service.schemas import PASSWORD_MAX_LENGTH, AdminResponse, RegisterRequest, TokenResponse, UserResponse
from user_service.security import DUMMY_HASH, create_access_token, password_hash
from user_service.tables import users, admins


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.engine = create_engine(get_settings())
    yield
    await app.state.engine.dispose()


settings = get_settings()
SettingsDep = Annotated[Settings, Depends(get_settings)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]

app = FastAPI(
    title="CampusRun User Service",
    lifespan=lifespan,
    root_path=settings.root_path,  # empty when accessed directly; "/api/users" when behind the gateway    
    # None turns each docs page off
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)


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


@app.get("/health")
async def health(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> JSONResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "unreachable"},
        )
    return JSONResponse(content={"status": "ok", "database": "ok"})


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, conn: Connection) -> UserResponse:
    # Argon2 is deliberately slow; hashing in a thread keeps other requests responsive
    hashed = await run_in_threadpool(password_hash.hash, body.password)

    # Relies on the case-insensitive unique indexes, so concurrent sign-ups can't both succeed
    created = (
        await conn.execute(
            insert(users)
            .values(email=body.email, username=body.username, password_hash=hashed)
            .on_conflict_do_nothing()
            .returning(
                users.c.id,
                users.c.email,
                users.c.username,
                users.c.email_verified_at,
                users.c.created_at,
            )
        )
    ).one_or_none()
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already in use",
        )
    return UserResponse.model_validate(created, from_attributes=True)


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
    return TokenResponse(access_token=create_access_token(row.id, "student", settings))


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

# Useing the CurrentUser type annotation for the endpoint parameter makes FastAPI run require_user first, which returns 401/403 before the endpoint runs; the parameter name doesn't matter.
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