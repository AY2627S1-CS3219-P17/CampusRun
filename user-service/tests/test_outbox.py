# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated tests for the transactional outbox: the OpenWallet message written with a registration or the
#        initial admin, the relay's publishing, ordering and retries, and the resync-wallets command.
# Author review: reviewed by Aaron

import asyncio

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from user_service.config import Settings
from user_service.outbox import publish_pending
from user_service.scripts.create_admin import create_initial_admin
from user_service.scripts.resync_wallets import resync_wallets
from user_service.tables import outbox, users

pytestmark = pytest.mark.anyio

VALID = {"email": "alice@u.nus.edu", "username": "alice", "password": "S3cret-pass"}


class FakePublisher:
    def __init__(self, fail_on: set[int] | None = None):
        self.sent: list[dict] = []
        self.fail_on = fail_on or set()

    async def publish(self, row) -> None:
        if row.payload["userId"] in self.fail_on:
            raise ConnectionError("broker down")
        await asyncio.sleep(0.01)  # let concurrent relays interleave
        self.sent.append(row.payload)


async def outbox_rows(engine: AsyncEngine) -> list:
    async with engine.connect() as conn:
        return list(await conn.execute(select(outbox).order_by(outbox.c.id)))


async def add_users(engine: AsyncEngine, count: int) -> list[int]:
    async with engine.begin() as conn:
        result = await conn.execute(
            insert(users)
            .values([{"email": f"u{i}@u.nus.edu", "username": f"u{i}", "password_hash": "x"} for i in range(count)])
            .returning(users.c.id)
        )
        return list(result.scalars())


async def test_registering_queues_an_open_wallet_message(client: AsyncClient, engine: AsyncEngine) -> None:
    response = await client.post("/auth/register", json=VALID)
    assert response.status_code == 201

    [row] = await outbox_rows(engine)
    assert (row.exchange, row.routing_key, row.message_type) == ("credit.commands", "wallet.open", "OpenWallet")
    assert row.payload == {"userId": response.json()["id"]}
    assert row.published_at is None
    assert len(row.message_id) == 36


async def test_a_failed_registration_queues_nothing(client: AsyncClient, engine: AsyncEngine) -> None:
    await client.post("/auth/register", json=VALID)
    duplicate = await client.post("/auth/register", json=VALID)
    assert duplicate.status_code == 409
    assert len(await outbox_rows(engine)) == 1


async def test_the_initial_admin_gets_a_wallet_too(engine: AsyncEngine, database_url: str) -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr(database_url),
        initial_admin_email="root@u.nus.edu",
        initial_admin_username="root",
        initial_admin_password=SecretStr("S3cret-pass"),
    )
    await create_initial_admin(settings)
    async with engine.connect() as conn:
        admin_id = await conn.scalar(select(users.c.id))
    assert [r.payload for r in await outbox_rows(engine)] == [{"userId": admin_id}]


async def test_relay_publishes_in_order_and_marks_each_message(engine: AsyncEngine, database_url: str) -> None:
    ids = await add_users(engine, 3)
    await resync_wallets(Settings(_env_file=None, database_url=SecretStr(database_url)))  # pyright: ignore[reportCallIssue]
    publisher = FakePublisher()

    assert await publish_pending(engine, publisher) == (3, False)
    assert publisher.sent == [{"userId": i} for i in ids]
    rows = await outbox_rows(engine)
    assert all(r.published_at is not None and r.attempts == 1 for r in rows)
    # Nothing left to send
    assert await publish_pending(engine, publisher) == (0, False)


async def test_relay_keeps_a_failed_message_for_later(engine: AsyncEngine, database_url: str) -> None:
    ids = await add_users(engine, 3)
    await resync_wallets(Settings(_env_file=None, database_url=SecretStr(database_url)))  # pyright: ignore[reportCallIssue]

    assert await publish_pending(engine, FakePublisher(fail_on={ids[1]})) == (1, True)
    first, second, third = await outbox_rows(engine)
    assert first.published_at is not None
    assert second.published_at is None and second.attempts == 1 and "broker down" in second.last_error
    # Stops at the failure, so messages keep their order
    assert third.published_at is None and third.attempts == 0

    later = FakePublisher()
    assert await publish_pending(engine, later) == (2, False)
    assert later.sent == [{"userId": ids[1]}, {"userId": ids[2]}]


async def test_two_relays_never_send_the_same_message(engine: AsyncEngine, database_url: str) -> None:
    await add_users(engine, 20)
    await resync_wallets(Settings(_env_file=None, database_url=SecretStr(database_url)))  # pyright: ignore[reportCallIssue]
    one, two = FakePublisher(), FakePublisher()
    await asyncio.gather(publish_pending(engine, one, batch_size=5), publish_pending(engine, two, batch_size=5))
    sent = one.sent + two.sent
    assert len(sent) == len({p["userId"] for p in sent}) == 10


async def test_resync_queues_one_message_per_user(engine: AsyncEngine, database_url: str) -> None:
    ids = await add_users(engine, 4)
    count = await resync_wallets(Settings(_env_file=None, database_url=SecretStr(database_url)))  # pyright: ignore[reportCallIssue]
    assert count == 4
    assert sorted(r.payload["userId"] for r in await outbox_rows(engine)) == ids
