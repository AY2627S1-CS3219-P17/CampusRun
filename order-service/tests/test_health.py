# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated tests for the health check.
# Author review: <to be completed by author>

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from order_service.db import get_engine
from order_service.main import app

pytestmark = pytest.mark.anyio


async def test_health_reports_the_database(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_is_503_when_the_database_is_unreachable() -> None:
    # Nothing listens on port 1
    unreachable = create_async_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
    app.dependency_overrides[get_engine] = lambda: unreachable
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()
        await unreachable.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}
