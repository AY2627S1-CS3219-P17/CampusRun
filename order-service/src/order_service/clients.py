# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated HTTP clients for the Supplier, User and Credit Services: supplier details and search,
#        usernames, and the advisory wallet check, each degrading cleanly when the other service is down; supplier
#        details and usernames are fetched in batches of up to 100 ids per request.
# Author review: <to be completed by author>

"""Reads from the other services, made as the signed-in user (their access token is forwarded).

Only reads: credits change through RabbitMQ commands (outbox.py), never through these calls.

Two kinds of call, with different behaviour when the other service is down:
    decorations   supplier details and usernames shown on errands. A failure leaves them out (None), so lists
                  and details still load; the web client shows a placeholder.
    decisions     whether the chosen supplier exists and is active, before an errand is created. A failure is a
                  503, because guessing would create an errand that can't be fulfilled.

The wallet check and the supplier search sit in between: they help but aren't needed, so a failure skips them and
the caller is told (None).
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import ValidationError

from order_service.config import Settings
from order_service.errors import FieldError
from order_service.schemas import SupplierSummary

log = logging.getLogger(__name__)

# supplier-service's largest page
SUPPLIER_PAGE_SIZE = 100
# The most ids supplier-service's /lookup and user-service's /internal/usernames take in one request
IDS_PER_REQUEST = 100


def _batches(ids: set[int]) -> list[list[int]]:
    ordered = sorted(ids)
    return [ordered[i : i + IDS_PER_REQUEST] for i in range(0, len(ordered), IDS_PER_REQUEST)]


class Unavailable(Exception):
    """The other service didn't answer, or answered with something unexpected."""


@dataclass(frozen=True)
class WalletBalance:
    # ACTIVE, or PENDING while the wallet is still being opened after registration
    status: str
    # None while PENDING
    available: int | None


class ServiceClients:
    """One pooled HTTP client for all calls to other services, created with the app (see main.py)."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.supplier_url = settings.supplier_service_url.rstrip("/")
        self.user_url = settings.user_service_url.rstrip("/")
        self.credit_url = settings.credit_api_url.rstrip("/")
        self.http = httpx.AsyncClient(timeout=settings.service_timeout_seconds, transport=transport)

    async def close(self) -> None:
        await self.http.aclose()

    async def _get(self, url: str, token: str, params: dict | None = None) -> httpx.Response:
        try:
            return await self.http.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            # The URL can carry ids but never credentials, so it's safe to log the host
            log.warning("%s is unreachable (%s)", httpx.URL(url).host, type(exc).__name__)
            raise Unavailable from None

    def _json(self, response: httpx.Response):
        if response.status_code != 200:
            log.warning("%s answered %d", response.url.host, response.status_code)
            raise Unavailable
        try:
            return response.json()
        except ValueError:
            raise Unavailable from None

    # ---------------------------------------------------------------- suppliers

    async def _supplier(self, supplier_id: int, token: str) -> SupplierSummary | None:
        response = await self._get(f"{self.supplier_url}/{supplier_id}", token)
        if response.status_code == 404:
            return None
        try:
            return SupplierSummary.model_validate(self._json(response))
        except ValidationError:
            raise Unavailable from None

    async def get_suppliers(self, ids: set[int], token: str) -> dict[int, SupplierSummary] | None:
        """Suppliers by id, in batches of 100 (GET /lookup). Unknown ids are left out; None if the service is down.

        Deactivated suppliers are included, so old errands can still show where the pickup was.
        """
        if not ids:
            return {}
        try:
            responses = await asyncio.gather(
                *(self._get(f"{self.supplier_url}/lookup", token, {"ids": batch}) for batch in _batches(ids))
            )
            found = [SupplierSummary.model_validate(item) for r in responses for item in self._json(r)]
        except Unavailable:
            return None
        except (ValidationError, TypeError):
            log.warning("supplier-service sent suppliers in an unexpected shape")
            return None
        return {s.id: s for s in found}

    async def require_active_supplier(self, supplier_id: int, token: str) -> SupplierSummary:
        """For creating or editing an errand: the supplier must exist and be active."""
        try:
            supplier = await self._supplier(supplier_id, token)
        except Unavailable:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Suppliers can't be checked right now. Try again in a moment."
            ) from None
        if supplier is None or not supplier.active:
            raise FieldError("supplierId", "Choose a supplier from the list.")
        return supplier

    async def _supplier_ids_matching(self, q: str, active: bool, token: str) -> set[int]:
        ids: set[int] = set()
        page = 1
        while True:
            data = self._json(
                await self._get(
                    f"{self.supplier_url}/",
                    token,
                    {"q": q, "active": str(active).lower(), "page": page, "pageSize": SUPPLIER_PAGE_SIZE},
                )
            )
            try:
                ids.update(int(item["id"]) for item in data["items"])
                if page >= data["totalPages"]:
                    return ids
            except (KeyError, TypeError, ValueError):
                raise Unavailable from None
            page += 1

    async def search_supplier_ids(self, q: str, token: str) -> set[int] | None:
        """Ids of suppliers whose name, building or description matches q, active or not. None if it's down.

        Deactivated suppliers are included, so errands whose supplier was later deactivated still match.
        """
        try:
            active, inactive = await asyncio.gather(
                self._supplier_ids_matching(q, True, token), self._supplier_ids_matching(q, False, token)
            )
        except Unavailable:
            return None
        return active | inactive

    # -------------------------------------------------------------------- users

    async def get_usernames(self, ids: set[int], token: str) -> dict[int, str] | None:
        """Usernames by user id (never emails). Unknown ids are left out; None if the service is down."""
        if not ids:
            return {}
        try:
            responses = await asyncio.gather(
                *(self._get(f"{self.user_url}/internal/usernames", token, {"ids": batch}) for batch in _batches(ids))
            )
            names: dict[int, str] = {}
            for response in responses:
                for item in self._json(response):
                    names[int(item["id"])] = str(item["username"])
            return names
        except Unavailable:
            return None
        except (KeyError, TypeError, ValueError):
            log.warning("user-service sent usernames in an unexpected shape")
            return None

    # ------------------------------------------------------------------ credits

    async def get_wallet(self, token: str) -> WalletBalance | None:
        """The signed-in user's balance, for an early "not enough credits" message. None if it can't be read.

        Advisory only: the Credit Service's reserve is the real check (docs/order-service-plan.md, section 6).
        """
        try:
            data = self._json(await self._get(f"{self.credit_url}/wallets/me", token))
            return WalletBalance(status=str(data["status"]), available=data["available"])
        except Unavailable:
            return None
        except (KeyError, TypeError):
            log.warning("credit-service sent a wallet in an unexpected shape")
            return None


def get_clients(request: Request) -> ServiceClients:
    return request.app.state.clients


Clients = Annotated[ServiceClients, Depends(get_clients)]
