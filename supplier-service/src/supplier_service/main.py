# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review and debugging for FastAPI app, lifespan and health check, following user-service/main.py.
# Author review: <to be completed by author>

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from supplier_service.config import get_settings
from supplier_service.db import create_engine, get_engine
from supplier_service.errors import install_error_handlers
from supplier_service.routes import delivery_locations, meta, suppliers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.engine = create_engine(get_settings())
    yield
    await app.state.engine.dispose()


app = FastAPI(title="CampusRun Supplier Service", lifespan=lifespan)

if get_settings().cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
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


app.include_router(suppliers.router)
app.include_router(delivery_locations.router)
app.include_router(meta.router)
