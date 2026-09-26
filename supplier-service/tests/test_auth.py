# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review for tests for access control (401 vs 403) and the health check;
#        AI-updated paths after the /suppliers prefix was removed, and tokens for the "type" claim (Claude Code, 2026-09-27).
# Author review: <to be completed by author>

import jwt
import pytest

from .conftest import ADMIN, STUDENT, TEST_SECRET, make_token, supplier_body

pytestmark = pytest.mark.anyio


async def test_health_needs_no_sign_in(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_no_token_is_401_with_bearer_challenge(client):
    response = await client.get("/")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Sign in to continue."


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        make_token(secret="some-other-secret-that-is-also-long-enough-000"),
        make_token(role="superuser"),
        jwt.encode({"sub": "x", "type": "admin", "exp": 9999999999}, None, algorithm="none"),
        # The old claim name, before the User Service's "type" claim was adopted
        jwt.encode({"sub": "x", "role": "admin", "exp": 9999999999}, TEST_SECRET, algorithm="HS256"),
    ],
    ids=["garbage", "wrong-secret", "unknown-type", "alg-none", "role-claim"],
)
async def test_invalid_tokens_are_401(client, token):
    response = await client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_expired_token_says_session_expired(client):
    response = await client.get("/", headers={"Authorization": f"Bearer {make_token(expires_in=-60)}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


async def test_token_without_expiry_is_rejected(client):
    token = jwt.encode({"sub": "x", "type": "admin"}, TEST_SECRET, algorithm="HS256")
    response = await client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_student_can_read(client):
    assert (await client.get("/", headers=STUDENT)).status_code == 200
    assert (await client.get("/meta", headers=STUDENT)).status_code == 200


@pytest.mark.parametrize("path", ["/", "/delivery-locations"])
async def test_student_cannot_create(client, path):
    response = await client.post(path, headers=STUDENT, json=supplier_body())
    assert response.status_code == 403
    assert response.json()["detail"] == "Only administrators can make this change."


async def test_student_cannot_edit_or_delete(client):
    created = (await client.post("/", headers=ADMIN, json=supplier_body())).json()
    url = f"/{created['id']}"
    assert (await client.patch(url, headers=STUDENT, json={"name": "Hacked"})).status_code == 403
    assert (await client.delete(url, headers=STUDENT)).status_code == 403
    assert (await client.get(url, headers=STUDENT)).json()["name"] == "Test Kiosk"


async def test_admin_identity_is_recorded(client):
    headers = {"Authorization": f"Bearer {make_token('admin', '42')}"}
    created = (await client.post("/", headers=headers, json=supplier_body())).json()
    assert created["createdBy"] == "42"
    assert created["updatedBy"] == "42"
