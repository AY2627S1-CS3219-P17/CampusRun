# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for FastAPI app, lifespan and health check, following supplier-service/main.py.
# Author review: <to be completed by author>

"""The credit service's HTTP API: read-only views of wallets, reservations and the audit.

Balances only change through RabbitMQ commands, applied by the separate credit-worker process.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from credit_service.config import get_settings
from credit_service.db import create_engine, get_engine
from credit_service.errors import install_error_handlers
from credit_service.routes import reservations, wallets


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.engine = create_engine(get_settings())
    yield
    await app.state.engine.dispose()


settings = get_settings()
if settings.jwt_secret is None:
    raise RuntimeError("Set JWT_SECRET (the User Service's token signing secret) to run the API")

app = FastAPI(
    title="CampusRun Credit Service",
    lifespan=lifespan,
    root_path=settings.root_path,  # empty when accessed directly; "/api/credits" when behind the gateway
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

install_error_handlers(app)


@app.get("/health", tags=["meta"])
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


app.include_router(wallets.router)
app.include_router(reservations.router)
