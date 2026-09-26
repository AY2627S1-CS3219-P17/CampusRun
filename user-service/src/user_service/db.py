# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-25
# Scope: AI-generated async SQLAlchemy engine factory and per-request transaction dependency;
#        AI-scoped the transaction to the endpoint so it commits before the response is sent.
# Author review: reviewed by Nathan

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from user_service.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
    )


def get_engine(request: Request) -> AsyncEngine:
    return request.app.state.engine


async def get_connection(
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> AsyncIterator[AsyncConnection]:
    # One transaction per request: commits on success, rolls back on error
    async with engine.begin() as conn:
        yield conn


# scope="function" commits before the response is sent, so a failed commit can't return success
Connection = Annotated[AsyncConnection, Depends(get_connection, scope="function")]
