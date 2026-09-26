# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated FastAPI app with engine lifespan and GET /health endpoint; AI-updated lifespan return type to AsyncGenerator and made API docs depend on ENABLE_DOCS.
# Author review: <to be completed by author>

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import get_settings
from user_service.db import create_engine, get_engine


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
