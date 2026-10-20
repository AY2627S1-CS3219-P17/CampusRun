# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated tests pinning the existing POST /autofill behaviour after it moved into routes/autofill.py,
#        with Groq and the Supplier Service replaced by a fake HTTP transport.
# Tool: OpenAI Codex (GPT-6), date: 2026-10-20
# Scope: Tested predefined delivery-location matching and custom-field fallback.
# Author review: <to be completed by author>

import json
from datetime import datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from order_service.routes import autofill
from tests.conftest import auth, make_token
from tests.factories import add_location

pytestmark = pytest.mark.anyio

PROMPT = "Pick up my printed notes from the COM3 print shop and deliver them to COM2 by 5pm. 10 credits."
SUPPLIERS = [{"id": 7, "name": "Printer @ Com 2"}, {"id": 9, "name": "Robot Cafe"}]


def extraction(**overrides) -> dict:
    fields = {
        "title": "Collect printed notes",
        "supplierName": "printer @ com 2",
        "building": "COM2",
        "floor": "1",
        "description": "Outside LT19",
        "deliveryBy": None,
        "credits": "10",
    }
    return fields | overrides


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch):
    """Answers the Groq and Supplier Service calls the endpoint makes, and records them."""
    state: dict = {"groq": lambda: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(extraction())}}]}), "calls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append(request)
        if request.url.host == "api.groq.com":
            return state["groq"]()
        return httpx.Response(200, json={"items": SUPPLIERS, "totalPages": 1})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        autofill.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    monkeypatch.setattr(autofill.settings, "groq_api_key", SecretStr("test-groq-key"))
    return state


async def test_requires_a_token(client: AsyncClient) -> None:
    response = await client.post("/autofill", json={"description": PROMPT})
    assert response.status_code == 401


async def test_rejects_an_expired_token(client: AsyncClient) -> None:
    expired = make_token(expires_in=-10)
    response = await client.post("/autofill", json={"description": PROMPT}, headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Your session has expired. Sign in again."


async def test_rejects_a_short_description(client: AsyncClient) -> None:
    response = await client.post("/autofill", json={"description": "too short"}, headers=auth())
    assert response.status_code == 422
    assert response.json()["errors"] == {"description": "Description must be 20 to 500 characters"}


async def test_is_503_without_a_groq_key(client: AsyncClient) -> None:
    response = await client.post("/autofill", json={"description": PROMPT}, headers=auth())
    assert response.status_code == 503
    assert response.json()["detail"] == "AI autofill is not configured."


async def test_fills_the_form_and_resolves_the_supplier(client: AsyncClient, fake_http) -> None:
    response = await client.post("/autofill", json={"description": PROMPT}, headers=auth(user_id=4))

    assert response.status_code == 200
    assert response.json() == {
        "title": "Collect printed notes",
        "supplier": {"id": 7, "name": "Printer @ Com 2"},
        "locationRef": None,
        "building": "COM2",
        "floor": "1",
        "description": "Outside LT19",
        "deliveryBy": None,
        "credits": 10,
    }
    supplier_call = next(c for c in fake_http["calls"] if c.url.host != "api.groq.com")
    # The supplier lookup is made as the signed-in user
    assert supplier_call.headers["Authorization"] == auth(user_id=4)["Authorization"]


async def test_drops_invalid_suggestions(client: AsyncClient, fake_http) -> None:
    too_soon = (datetime.now(autofill.CAMPUS_TZ) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    content = extraction(supplierName="Unknown Shop", credits="500", deliveryBy=too_soon, title="x" * 101)
    fake_http["groq"] = lambda: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    body = (await client.post("/autofill", json={"description": PROMPT}, headers=auth())).json()

    assert body["supplier"] is None
    assert body["credits"] is None
    assert body["deliveryBy"] is None
    assert body["title"] is None


async def test_reports_groq_rate_limits(client: AsyncClient, fake_http) -> None:
    fake_http["groq"] = lambda: httpx.Response(429)
    response = await client.post("/autofill", json={"description": PROMPT}, headers=auth())
    assert response.status_code == 429
    assert response.json()["detail"] == "AI autofill is busy. Try again shortly."


async def test_matches_a_predefined_delivery_location(client: AsyncClient, engine, fake_http) -> None:
    location_id = await add_location(
        engine,
        name="COM2 (LT19)",
        floor="2",
        description="Meet at the LT19 entrance.",
        latitude=1.29373,
        longitude=103.7743,
    )
    response = await client.post("/autofill", json={"description": PROMPT}, headers=auth())

    assert response.status_code == 200
    body = response.json()
    assert body["locationRef"] == {
        "id": location_id,
        "name": "COM2 (LT19)",
        "latitude": 1.29373,
        "longitude": 103.7743,
    }
    assert (body["building"], body["floor"], body["description"]) == (
        "COM2 (LT19)", "2", "Meet at the LT19 entrance."
    )


async def test_matches_a_unique_location_abbreviation(client: AsyncClient, engine, fake_http) -> None:
    location_id = await add_location(engine, name="Yusof Ishak House (YIH)")
    content = extraction(building="YIH")
    fake_http["groq"] = lambda: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    body = (await client.post("/autofill", json={"description": PROMPT}, headers=auth())).json()

    assert body["locationRef"]["id"] == location_id
    assert body["building"] == "Yusof Ishak House (YIH)"


async def test_ignores_inactive_and_personal_locations(client: AsyncClient, engine, fake_http) -> None:
    await add_location(engine, name="COM2", active=False)
    await add_location(engine, name="COM2", predefined=False, created_by=1)
    response = await client.post("/autofill", json={"description": PROMPT}, headers=auth())

    assert response.status_code == 200
    body = response.json()
    assert body["locationRef"] is None
    assert (body["building"], body["floor"], body["description"]) == ("COM2", "1", "Outside LT19")


async def test_ambiguous_abbreviation_keeps_custom_fields(client: AsyncClient, engine, fake_http) -> None:
    await add_location(engine, name="Yusof Ishak House (YIH)")
    await add_location(engine, name="Yet Another House (YIH)")
    content = extraction(building="YIH")
    fake_http["groq"] = lambda: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    body = (await client.post("/autofill", json={"description": PROMPT}, headers=auth())).json()

    assert body["locationRef"] is None
    assert body["building"] == "YIH"
