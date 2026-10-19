# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Defined partial autofill contracts and a strict model schema with delivery-only location details and nullable string credits.
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-added the camelCase base models, the paged list shape and the delivery location models, copied from
#        supplier-service/schemas.py, with optional floor and description; the supplier summary and the errand
#        request, response and list models, and the errand edit model (2026-10-19).
# Author review: <to be completed by author>

"""Request and response models. Every value from a client is checked here.

JSON uses camelCase to match the web client's types; Python code uses the snake_case field names.
"""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from order_service.config import get_settings
from order_service.errors import FieldError
from order_service.states import CancelReason, CreditStatus, State
from order_service.tables import (
    FLOOR_MAX_LENGTH,
    LOCATION_DESCRIPTION_MAX_LENGTH,
    LOCATION_NAME_MAX_LENGTH,
    REWARD_MAX,
    REWARD_MIN,
    TITLE_MAX_LENGTH,
)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class RequestModel(CamelModel):
    model_config = ConfigDict(extra="forbid")


def _text(max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)]


def _check_latitude(value: float) -> float:
    s = get_settings()
    if not s.served_area_min_lat <= value <= s.served_area_max_lat:
        raise ValueError(
            f"Latitude must be inside the NUS served area ({s.served_area_min_lat} to {s.served_area_max_lat})."
        )
    return value


def _check_longitude(value: float) -> float:
    s = get_settings()
    if not s.served_area_min_lng <= value <= s.served_area_max_lng:
        raise ValueError(
            f"Longitude must be inside the NUS served area ({s.served_area_min_lng} to {s.served_area_max_lng})."
        )
    return value


LocationName = _text(LOCATION_NAME_MAX_LENGTH)
Floor = _text(FLOOR_MAX_LENGTH)
LocationDescription = _text(LOCATION_DESCRIPTION_MAX_LENGTH)
Latitude = Annotated[float, AfterValidator(_check_latitude)]
Longitude = Annotated[float, AfterValidator(_check_longitude)]


class Page[T](CamelModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# ------------------------------------------------------- delivery locations


class DeliveryLocationCreate(RequestModel):
    name: LocationName
    floor: Floor | None = None
    description: LocationDescription | None = None
    latitude: Latitude
    longitude: Longitude
    active: bool = True
    # Admins only: add it to the shared campus list instead of your own locations
    predefined: bool = False


class DeliveryLocationUpdate(RequestModel):
    """PATCH body. Only the fields sent change. null clears floor or description."""

    name: LocationName | None = None
    floor: Floor | None = None
    description: LocationDescription | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    active: bool | None = None

    @field_validator("name", "latitude", "longitude", "active", mode="before")
    @classmethod
    def fields_cannot_be_cleared(cls, value):
        if value is None:
            raise ValueError("This field is required and cannot be empty.")
        return value

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        return self


class DeliveryLocationOut(CamelModel):
    id: int
    name: str
    floor: str | None
    description: str | None
    latitude: float
    longitude: float
    active: bool
    predefined: bool
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


# ----------------------------------------------------------- other services


class SupplierSummary(CamelModel):
    """The parts of a Supplier Service supplier that errands show. Fetched live, never stored (D6)."""

    id: int
    name: str
    building: str
    floor: str | None
    latitude: float
    longitude: float
    active: bool


# ------------------------------------------------------------------ errands

# The create-request form's rules for deliverBy (frontend/src/components/shared/update-request.tsx)
MIN_LEAD = timedelta(minutes=15)
MAX_LEAD = timedelta(hours=24)

Title = _text(TITLE_MAX_LENGTH)
Credits = Annotated[int, Field(ge=REWARD_MIN, le=REWARD_MAX)]


def check_deliver_by(value: datetime, now: datetime | None = None) -> datetime:
    """Campus time if no time zone is given; between 15 minutes and 24 hours from now."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(get_settings().timezone))
    now = now or datetime.now(value.tzinfo)
    if value < now + MIN_LEAD:
        raise ValueError("Choose a time at least 15 minutes from now.")
    if value > now + MAX_LEAD:
        raise ValueError("Choose a time within the next 24 hours.")
    return value


DeliverBy = Annotated[datetime, AfterValidator(check_deliver_by)]


class ErrandCreate(RequestModel):
    """POST / body. The delivery point is either an existing location (deliveryLocationId: a predefined one or one
    of your own) or a new one of your own (building, floor, description, latitude, longitude), as the form sends."""

    title: Title
    supplier_id: Annotated[int, Field(ge=1)]
    delivery_location_id: Annotated[int, Field(ge=1)] | None = None
    building: LocationName | None = None
    floor: Floor | None = None
    description: LocationDescription | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    deliver_by: DeliverBy
    credits: Credits

    @model_validator(mode="after")
    def one_delivery_point(self):
        custom = {"building", "floor", "description", "latitude", "longitude"} & self.model_fields_set
        if self.delivery_location_id is not None:
            if custom:
                raise ValueError("Choose a saved delivery location or enter a new one, not both.")
            return self
        missing = [f for f in ("building", "latitude", "longitude") if getattr(self, f) is None]
        if missing:
            raise FieldError(missing[0], "This field is required.")
        return self


class ErrandUpdate(RequestModel):
    """PATCH /{id} body, while the errand is OPEN. Only the fields sent change.

    A new delivery point works as on create: deliveryLocationId, or building, floor, description, latitude and
    longitude for a new location of your own. Changing that location's own details is PATCH /delivery-locations/{id}.
    """

    title: Title | None = None
    supplier_id: Annotated[int, Field(ge=1)] | None = None
    delivery_location_id: Annotated[int, Field(ge=1)] | None = None
    building: LocationName | None = None
    floor: Floor | None = None
    description: LocationDescription | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    deliver_by: DeliverBy | None = None
    credits: Credits | None = None

    @field_validator("title", "supplier_id", "delivery_location_id", "deliver_by", "credits", mode="before")
    @classmethod
    def fields_cannot_be_cleared(cls, value):
        if value is None:
            raise ValueError("This field is required and cannot be empty.")
        return value

    @model_validator(mode="after")
    def check_changes(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        # Intersection operation on Sets
        custom = {"building", "floor", "description", "latitude", "longitude"} & self.model_fields_set
        if custom:
            if self.delivery_location_id is not None:
                raise ValueError("Choose a saved delivery location or enter a new one, not both.")
            # Prevent creating a new incomplete delivery location
            missing = [f for f in ("building", "latitude", "longitude") if getattr(self, f) is None]
            if missing:
                raise FieldError(missing[0], "This field is required.")
        return self


class ErrandSort(StrEnum):
    # The frontend's ERRAND_SORTS values (frontend/src/utils/toolbar.ts)
    MOST_RECENT = "most-recent"
    LEAST_RECENT = "least-recent"
    MOST_CREDITS = "most-credits"
    LEAST_CREDITS = "least-credits"


class ErrandTab(StrEnum):
    # My Requests and My Tasks (there is no pending tab: D4)
    ACTIVE = "active"
    COMPLETED = "completed"
    INACTIVE = "inactive"


class ErrandLocation(CamelModel):
    id: int
    name: str
    floor: str | None
    description: str | None
    latitude: float
    longitude: float
    predefined: bool


class ErrandOut(CamelModel):
    id: int
    title: str
    state: State
    # PENDING while a credit command is on its way; the web client shows "credits processing" (D4)
    credit_status: CreditStatus
    credit_rejection: str | None
    credits: int
    requester_id: int
    # Null if the User Service can't be reached
    requester_name: str | None
    courier_id: int | None
    courier_name: str | None
    supplier_id: int
    # Live from the Supplier Service (D6); null if it can't be reached
    supplier: SupplierSummary | None
    delivery_location: ErrandLocation
    # deliver_by: the actual deadline
    deliver_by: datetime
    # expires_at: if the errand has been delivered, this is the deadline for the requester to confirm
    expires_at: datetime
    cancel_reason: CancelReason | None
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    expired_at: datetime | None


class ErrandPage(Page[ErrandOut]):
    # False when a search couldn't include supplier names because the Supplier Service was down
    supplier_search: bool = True


# ------------------------------------------------------------------ autofill


class AutofillRequest(BaseModel):
    description: str

    @field_validator("description")
    @classmethod
    def meaningful_description(cls, value: str) -> str:
        value = value.strip()
        if not 20 <= len(value) <= 500:
            raise ValueError("Description must be 20 to 500 characters")
        return value


class SupplierRef(BaseModel):
    id: int
    name: str


class AutofillResponse(BaseModel):
    title: str | None
    supplier: SupplierRef | None
    building: str | None
    floor: str | None
    description: str | None
    deliveryBy: str | None
    credits: int | None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None
    supplierName: str | None
    building: str | None
    floor: str | None
    description: str | None
    deliveryBy: str | None
    credits: str | None


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": ["string", "null"],
            "description": "Clear errand title, at most 100 characters; rewrite concisely.",
        },
        "supplierName": {
            "type": ["string", "null"],
            "description": "Exact pickup supplier name, at most 100 characters; do not abbreviate.",
        },
        "building": {
            "type": ["string", "null"],
            "description": "Only the stated delivery building, at most 100 characters; never the supplier or pickup building.",
        },
        "floor": {
            "type": ["string", "null"],
            "description": "Only the stated delivery floor, at most 10 characters; null when absent.",
        },
        "description": {
            "type": ["string", "null"],
            "description": "Only details describing or locating the delivery building, at most 200 characters; no item, supplier, or pickup details. Null when absent.",
        },
        "deliveryBy": {"type": ["string", "null"]},
        "credits": {
            "type": ["string", "null"],
            "description": "Whole-number reward as a string of digits, or null.",
        },
    },
    # Strict mode requires every key; null still means the form field is optional.
    "required": [
        "title", "supplierName", "building", "floor", "description", "deliveryBy", "credits"
    ],
    "additionalProperties": False,
}