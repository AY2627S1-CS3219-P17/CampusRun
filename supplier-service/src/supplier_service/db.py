# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated engine factory and per-request transaction, following user-service/db.py.
# Author review: <to be completed by author>

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from supplier_service.config import Settings


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


# scope="function" closes the transaction (commits) before the response is sent.
# With the default scope, FastAPI 0.141 sends the response first, so a client
# could get "201 Created" before the row is committed, or even if the commit fails.
Connection = Annotated[AsyncConnection, Depends(get_connection, scope="function")]
