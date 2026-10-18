# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for HTTP response models for wallets, ledger entries and reservations.
# Author review: <to be completed by author>

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from credit_service.tables import EntryKind, ReservationStatus


class _Response(BaseModel):
    # camelCase JSON, like the other services' web client types
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True, from_attributes=True)


class WalletStatus(StrEnum):
    ACTIVE = "ACTIVE"
    # Registered, but the OpenWallet message hasn't been applied yet: the initial credits are on their way
    PENDING = "PENDING"


class WalletResponse(_Response):
    user_id: int
    status: WalletStatus
    # Null while PENDING
    available: int | None
    reserved: int | None
    total: int | None
    updated_at: datetime | None


class LedgerEntryResponse(_Response):
    id: int
    errand_id: int | None
    kind: EntryKind
    available_change: int
    reserved_change: int
    available_after: int
    reserved_after: int
    created_at: datetime


class LedgerPage(_Response):
    items: list[LedgerEntryResponse]
    limit: int
    offset: int


class ReservationResponse(_Response):
    errand_id: int
    requester_id: int
    courier_id: int | None
    amount: int
    status: ReservationStatus
    reason: str | None
    created_at: datetime
    updated_at: datetime
