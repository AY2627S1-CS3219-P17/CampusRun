# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated FastAPI app with engine lifespan and GET /health endpoint; AI-updated lifespan return type to AsyncGenerator and made API docs depend on ENABLE_DOCS;
#        AI-completed the POST /auth/register endpoint from the author's draft.
# Author review: reviewed by Nathan

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import get_settings
from user_service.db import Connection, create_engine, get_engine
from user_service.schemas import RegisterRequest, UserResponse
from user_service.security import password_hash
from user_service.tables import users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.engine = create_engine(get_settings())
    yield
    await app.state.engine.dispose()


settings = get_settings()

app = FastAPI(
    title="CampusRun User Service",
    lifespan=lifespan,
    # None turns each docs page off
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)


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
