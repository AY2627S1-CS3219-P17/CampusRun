# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated tests for the Supplier, User and Credit Service clients, with the services replaced by a fake
#        HTTP transport: what each call returns, the forwarded token, and what happens when a service is down.
# Author review: <to be completed by author>

from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from order_service.clients import ServiceClients, WalletBalance
from order_service.config import Settings
from order_service.errors import FieldError

pytestmark = pytest.mark.anyio

TOKEN = "the-users-token"
SETTINGS = Settings(
    _env_file=None,  # pyright: ignore[reportCallIssue]
    database_url=SecretStr("postgresql+asyncpg://unused@localhost/unused"),
    supplier_service_url="http://suppliers",
    user_service_url="http://users",
    credit_api_url="http://credits",
)


def supplier(supplier_id: int, name: str = "Robot Cafe", active: bool = True) -> dict:
    # The fields the Supplier Service sends that the client reads, plus some it ignores
    return {
        "id": supplier_id,
        "name": name,
        "type": "Drinks",
        "building": "COM3",
        "floor": "1",
        "latitude": 1.2949,
        "longitude": 103.7744,
        "active": active,
        "isOpenNow": True,
    }


class FakeServices:
    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def clients_for(handler: Callable[[httpx.Request], httpx.Response]) -> tuple[ServiceClients, FakeServices]:
    fake = FakeServices(handler)
    return ServiceClients(SETTINGS, transport=httpx.MockTransport(fake)), fake


def down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


# ---------------------------------------------------------------- suppliers


def requested_ids(request: httpx.Request) -> list[int]:
    return [int(i) for i in parse_qs(request.url.query.decode())["ids"]]


async def test_get_suppliers_looks_up_ids_in_batches_of_100_as_the_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/lookup"
        ids = requested_ids(request)
        assert len(ids) <= 100
        # Supplier 150 doesn't exist; supplier 3 was deactivated
        return httpx.Response(200, json=[supplier(i, f"Supplier {i}", active=i != 3) for i in ids if i != 150])

    clients, fake = clients_for(handler)
    found = await clients.get_suppliers(set(range(1, 151)), TOKEN)

    assert found is not None
    assert len(fake.requests) == 2
    # Unknown ids are left out; deactivated suppliers are still returned, so old errands can show them
    assert len(found) == 149 and 150 not in found
    assert found[1].name == "Supplier 1" and found[3].active is False
    assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in fake.requests)


async def test_get_suppliers_makes_no_call_for_no_ids() -> None:
    clients, fake = clients_for(down)
    assert await clients.get_suppliers(set(), TOKEN) == {}
    assert fake.requests == []


@pytest.mark.parametrize(
    "handler",
    [
        down,
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json=[{"id": 1}]),
    ],
    ids=["unreachable", "server-error", "bad-body", "bad-shape"],
)
async def test_get_suppliers_is_none_when_the_service_is_down(handler) -> None:
    clients, _ = clients_for(handler)
    assert await clients.get_suppliers({1}, TOKEN) is None


async def test_require_active_supplier_accepts_an_active_supplier() -> None:
    clients, _ = clients_for(lambda r: httpx.Response(200, json=supplier(5)))
    assert (await clients.require_active_supplier(5, TOKEN)).id == 5


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404, json={}), httpx.Response(200, json=supplier(5, active=False))],
    ids=["unknown", "deactivated"],
)
async def test_require_active_supplier_rejects_unknown_or_deactivated(response: httpx.Response) -> None:
    clients, _ = clients_for(lambda r: response)
    with pytest.raises(FieldError) as error:
        await clients.require_active_supplier(5, TOKEN)
    assert error.value.field == "supplierId"


async def test_require_active_supplier_is_503_when_the_service_is_down() -> None:
    clients, _ = clients_for(down)
    with pytest.raises(HTTPException) as error:
        await clients.require_active_supplier(5, TOKEN)
    assert error.value.status_code == 503


async def test_supplier_search_covers_active_and_deactivated_suppliers_and_every_page() -> None:
    # Active: two pages of results; deactivated: one
    pages = {("true", "1"): ([1, 2], 2), ("true", "2"): ([3], 2), ("false", "1"): ([7], 1)}

    def handler(request: httpx.Request) -> httpx.Response:
        query = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        assert query["q"] == "cafe" and query["pageSize"] == "100"
        ids, total_pages = pages[(query["active"], query["page"])]
        return httpx.Response(200, json={"items": [supplier(i) for i in ids], "totalPages": total_pages})

    clients, fake = clients_for(handler)
    assert await clients.search_supplier_ids("cafe", TOKEN) == {1, 2, 3, 7}
    assert len(fake.requests) == 3


async def test_supplier_search_with_no_matches_is_an_empty_set() -> None:
    clients, _ = clients_for(lambda r: httpx.Response(200, json={"items": [], "totalPages": 0}))
    assert await clients.search_supplier_ids("nothing", TOKEN) == set()


async def test_supplier_search_is_none_when_the_service_is_down() -> None:
    clients, _ = clients_for(down)
    assert await clients.search_supplier_ids("cafe", TOKEN) is None


# -------------------------------------------------------------------- users


async def test_get_usernames_looks_up_ids_in_batches_of_100() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/usernames"
        ids = requested_ids(request)
        assert len(ids) <= 100
        # User 150 doesn't exist any more
        return httpx.Response(200, json=[{"id": i, "username": f"user{i}"} for i in ids if i != 150])

    clients, fake = clients_for(handler)
    names = await clients.get_usernames(set(range(1, 151)), TOKEN)

    assert names is not None
    assert len(fake.requests) == 2
    assert names[1] == "user1" and 150 not in names and len(names) == 149
    assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in fake.requests)


@pytest.mark.parametrize(
    "handler",
    [down, lambda r: httpx.Response(404), lambda r: httpx.Response(200, json=[{"name": "no id"}])],
    ids=["unreachable", "not-found", "bad-shape"],
)
async def test_get_usernames_is_none_when_the_service_is_down(handler) -> None:
    clients, _ = clients_for(handler)
    assert await clients.get_usernames({1}, TOKEN) is None


async def test_get_usernames_makes_no_call_for_no_ids() -> None:
    clients, fake = clients_for(down)
    assert await clients.get_usernames(set(), TOKEN) == {}
    assert fake.requests == []


# ------------------------------------------------------------------ credits


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"userId": 1, "status": "ACTIVE", "available": 85, "reserved": 15, "total": 100}, WalletBalance("ACTIVE", 85)),
        ({"userId": 1, "status": "PENDING", "available": None, "reserved": None, "total": None}, WalletBalance("PENDING", None)),
    ],
    ids=["active", "pending"],
)
async def test_get_wallet_reads_the_users_balance(body: dict, expected: WalletBalance) -> None:
    clients, fake = clients_for(lambda r: httpx.Response(200, json=body))
    assert await clients.get_wallet(TOKEN) == expected
    assert fake.requests[0].url == "http://credits/wallets/me"


@pytest.mark.parametrize(
    "handler", [down, lambda r: httpx.Response(503), lambda r: httpx.Response(200, json={})], ids=["unreachable", "error", "bad-shape"]
)
async def test_get_wallet_is_none_when_it_cant_be_read(handler) -> None:
    clients, _ = clients_for(handler)
    assert await clients.get_wallet(TOKEN) is None
