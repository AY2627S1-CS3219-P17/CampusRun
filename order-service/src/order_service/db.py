# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: Engine factory and per-request transaction copied from credit-service/db.py; AI-added the Engine
#        dependency for endpoints that call other services (2026-10-19).
# Author review: <to be completed by author>

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from order_service.config import Settings


def create_engine(settings: Settings, **kwargs) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        **kwargs,
    )


def get_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


async def get_connection(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> AsyncIterator[AsyncConnection]:
    # One transaction per request: commits on success, rolls back on error
    async with engine.begin() as conn:
        yield conn


# scope="function" closes the transaction before the response is sent (see supplier-service/db.py)
Connection = Annotated[AsyncConnection, Depends(get_connection, scope="function")]
# For endpoints that also call other services: they open their own short transaction after (or between) those calls,
# so a slow service never holds a database connection
Engine = Annotated[AsyncEngine, Depends(get_engine)]
