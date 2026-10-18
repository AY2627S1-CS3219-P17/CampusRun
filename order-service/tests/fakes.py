# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated in-memory stand-ins for the Supplier, User and Credit Services, served through a fake HTTP
#        transport so the errand endpoints can be tested without the other services running.
# Author review: <to be completed by author>

from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import jwt
from pydantic import SecretStr

from order_service.clients import ServiceClients
from order_service.config import Settings

SETTINGS = Settings(
    _env_file=None,  # pyright: ignore[reportCallIssue]
    database_url=SecretStr("postgresql+asyncpg://unused@localhost/unused"),
    supplier_service_url="http://suppliers",
    user_service_url="http://users",
    credit_api_url="http://credits",
)


def supplier(supplier_id: int, name: str, *, active: bool = True, building: str = "COM3") -> dict:
    return {
        "id": supplier_id,
        "name": name,
        "type": "Food",
        "building": building,
        "floor": "1",
        "latitude": 1.2949,
        "longitude": 103.7744,
        "active": active,
        "isOpenNow": True,
    }


class FakeServices:
    """Answers the calls ServiceClients makes. Change the attributes in a test to set up a scenario."""

    def __init__(self):
        self.suppliers: dict[int, dict] = {
            1: supplier(1, "Robot Cafe"),
            2: supplier(2, "Printer @ Com 2", building="COM2"),
            3: supplier(3, "Old Noodle Shop", active=False),
        }
        # Usernames default to "user<id>"
        self.usernames: dict[int, str] = {}
        # Wallets default to ACTIVE with 100 available
        self.wallets: dict[int, dict] = {}
        # Hosts that are "down": "suppliers", "users", "credits"
        self.down: set[str] = set()
        self.requests: list[httpx.Request] = []
        # Called with each request before it's answered, e.g. to check what the caller holds meanwhile
        self.on_request: Callable[[httpx.Request], None] | None = None

    def clients(self) -> ServiceClients:
        return ServiceClients(SETTINGS, transport=httpx.MockTransport(self))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.on_request is not None:
            self.on_request(request)
        host = request.url.host
        if host in self.down:
            raise httpx.ConnectError("connection refused", request=request)
        query = parse_qs(request.url.query.decode())
        match host, request.url.path:
            case "suppliers", "/lookup":
                ids = sorted({int(i) for i in query["ids"]})
                return httpx.Response(200, json=[self.suppliers[i] for i in ids if i in self.suppliers])
            case "suppliers", "/":
                q = query.get("q", [""])[0].casefold()
                active = query["active"][0] == "true"
                found = [
                    s for s in self.suppliers.values()
                    if s["active"] is active and (q in s["name"].casefold() or q in s["building"].casefold())
                ]
                return httpx.Response(200, json={"items": found, "totalPages": 1 if found else 0})
            case "suppliers", path:
                found = self.suppliers.get(int(path.strip("/")))
                return httpx.Response(200, json=found) if found else httpx.Response(404, json={"detail": "Not found"})
            case "users", "/internal/usernames":
                ids = sorted({int(i) for i in query["ids"]})
                return httpx.Response(200, json=[{"id": i, "username": self.usernames.get(i, f"user{i}")} for i in ids])
            case "credits", "/wallets/me":
                token = request.headers["Authorization"].removeprefix("Bearer ")
                user_id = int(jwt.decode(token, options={"verify_signature": False})["sub"])
                wallet = self.wallets.get(user_id, {"status": "ACTIVE", "available": 100})
                return httpx.Response(200, json={"userId": user_id, **wallet})
        return httpx.Response(404)
