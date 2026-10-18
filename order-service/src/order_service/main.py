# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated FastAPI app, engine lifespan and health check, following credit-service/main.py; the autofill
#        endpoint (OpenAI Codex, 2026-10-17) now lives in routes/autofill.py; AI-added the delivery location routes.
# Author review: <to be completed by author>

"""The order service's HTTP API.

Credit commands are never sent from here: requests write them to the outbox table, and the separate order-worker
process publishes them (docs/order-service-plan.md).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from order_service.config import get_settings
from order_service.db import create_engine, get_engine
from order_service.errors import install_error_handlers
from order_service.routes import autofill, delivery_locations


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.engine = create_engine(get_settings())
    yield
    await app.state.engine.dispose()


settings = get_settings()
if settings.jwt_secret is None:
    raise RuntimeError("Set JWT_SECRET (the User Service's token signing secret) to run the API")

app = FastAPI(
    title="CampusRun Order Service",
    lifespan=lifespan,
    root_path=settings.root_path,  # empty when accessed directly; "/api/orders" when behind the gateway
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


# Routes at fixed paths go first. The errand routes added later have /{errand_id} at the root, which would otherwise
# catch /autofill, /me, /admin and /delivery-locations.
app.include_router(autofill.router)
app.include_router(delivery_locations.router)
