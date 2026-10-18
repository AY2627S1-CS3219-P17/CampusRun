# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Defined partial autofill contracts and a strict model schema with delivery-only location details and nullable string credits.
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-added the camelCase base models, the paged list shape and the delivery location models, copied from
#        supplier-service/schemas.py, with optional floor and description.
# Author review: <to be completed by author>

"""Request and response models. Every value from a client is checked here.

JSON uses camelCase to match the web client's types; Python code uses the snake_case field names.
"""

from datetime import datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from order_service.config import get_settings
from order_service.tables import FLOOR_MAX_LENGTH, LOCATION_DESCRIPTION_MAX_LENGTH, LOCATION_NAME_MAX_LENGTH


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