# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review for tests for the read-only HTTP API and the migrations-match-tables check.
# Author review: <to be completed by author>

import pytest
from alembic import command

from credit_service import ledger
from credit_service.commands import OpenWallet, ReserveCredits, TransferCredits

from .conftest import ALEMBIC_CONFIG, auth

pytestmark = pytest.mark.anyio

REQUESTER, COURIER, OTHER, ADMIN = 1, 2, 3, 4


async def setup_transfer(engine):
    async with engine.begin() as conn:
        for user_id in (REQUESTER, COURIER):
            await ledger.open_wallet(conn, OpenWallet(user_id=user_id), initial_credits=100)
        await ledger.reserve(conn, ReserveCredits(errand_id=7, requester_id=REQUESTER, amount=15))
        await ledger.reserve(conn, ReserveCredits(errand_id=8, requester_id=REQUESTER, amount=5))
        await ledger.transfer(conn, TransferCredits(errand_id=7, requester_id=REQUESTER, courier_id=COURIER))


async def test_health(client):
    response = await client.get("/health")
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_wallet_needs_a_session(client):
    assert (await client.get("/wallets/me")).status_code == 401
    expired = {"Authorization": "Bearer not-a-token"}
    assert (await client.get("/wallets/me", headers=expired)).status_code == 401


async def test_wallet_is_pending_until_the_open_wallet_message_is_applied(client, engine):
    response = await client.get("/wallets/me", headers=auth(REQUESTER))
    assert response.status_code == 200
    assert response.json() == {
        "userId": REQUESTER,
        "status": "PENDING",
        "available": None,
        "reserved": None,
        "total": None,
        "updatedAt": None,
    }
    async with engine.begin() as conn:
        await ledger.open_wallet(conn, OpenWallet(user_id=REQUESTER), initial_credits=100)
    body = (await client.get("/wallets/me", headers=auth(REQUESTER))).json()
    assert (body["status"], body["available"], body["reserved"], body["total"]) == ("ACTIVE", 100, 0, 100)


async def test_balances_before_and_after_a_transfer(client, engine):
    await setup_transfer(engine)
    requester = (await client.get("/wallets/me", headers=auth(REQUESTER))).json()
    courier = (await client.get("/wallets/me", headers=auth(COURIER))).json()
    assert (requester["available"], requester["reserved"], requester["total"]) == (80, 5, 85)
    assert (courier["available"], courier["reserved"], courier["total"]) == (115, 0, 115)


async def test_transactions_are_your_own_newest_first(client, engine):
    await setup_transfer(engine)
    body = (await client.get("/wallets/me/transactions", headers=auth(REQUESTER))).json()
    assert [(e["kind"], e["errandId"], e["availableChange"], e["reservedChange"]) for e in body["items"]] == [
        ("TRANSFER_OUT", 7, 0, -15),
        ("RESERVE", 8, -5, 5),
        ("RESERVE", 7, -15, 15),
        ("INITIAL_ALLOCATION", None, 100, 0),
    ]
    one_errand = (await client.get("/wallets/me/transactions?errandId=7", headers=auth(COURIER))).json()
    assert [e["kind"] for e in one_errand["items"]] == ["TRANSFER_IN"]
    paged = (await client.get("/wallets/me/transactions?limit=1&offset=1", headers=auth(REQUESTER))).json()
    assert [e["kind"] for e in paged["items"]] == ["RESERVE"]


async def test_transactions_validate_their_query(client):
    response = await client.get("/wallets/me/transactions?limit=0", headers=auth(REQUESTER))
    assert response.status_code == 422
    assert "limit" in response.json()["errors"]


async def test_a_reservation_is_visible_to_its_requester_courier_and_admins(client, engine):
    await setup_transfer(engine)
    for headers in (auth(REQUESTER), auth(COURIER), auth(ADMIN, "admin")):
        response = await client.get("/reservations/7", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "TRANSFERRED"
    assert (await client.get("/reservations/7", headers=auth(OTHER))).status_code == 404
    assert (await client.get("/reservations/999", headers=auth(REQUESTER))).status_code == 404


async def test_audit_is_for_admins_only(client, engine):
    await setup_transfer(engine)
    assert (await client.get("/admin/audit", headers=auth(REQUESTER))).status_code == 403
    body = (await client.get("/admin/audit", headers=auth(ADMIN, "admin"))).json()
    assert body["ok"] is True
    assert (body["totalAllocated"], body["totalInCirculation"], body["totalReserved"]) == (200, 200, 5)


async def test_no_endpoint_changes_a_balance(client):
    # F14.1.1: no way to buy, top up, withdraw or exchange credits over HTTP
    from credit_service.main import app

    methods = {m for route in app.routes for m in getattr(route, "methods", set())}
    assert methods <= {"GET", "HEAD"}


def test_migrations_match_tables():
    # Fails if tables.py was changed without a new Alembic migration
    command.check(ALEMBIC_CONFIG)
