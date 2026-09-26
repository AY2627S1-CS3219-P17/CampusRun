# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review and debugging for request/response models and validation rules. JSON field names
#        and supplier types follow frontend/src/types/supplier.ts.
# Author review: <to be completed by author>

"""Request and response models. Every value from a client is checked here (N8.2.1).

JSON uses camelCase (startTime, locationDescription) to match the web client's
types; Python code uses the snake_case field names.
"""

from datetime import datetime, time
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from supplier_service.config import get_settings
from supplier_service.tables import SUPPLIER_TYPES


class SupplierType(StrEnum):
    FOOD = "Food"
    DRINKS = "Drinks"
    SHOPPING = "Shopping"
    PRINTING = "Printing"


assert tuple(SupplierType) == SUPPLIER_TYPES, "SupplierType and the database check must match"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class RequestModel(CamelModel):
    model_config = ConfigDict(extra="forbid")


def _text(min_length: int, max_length: int):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)
    ]


def _max_500_chars(url: HttpUrl) -> HttpUrl:
    if len(str(url)) > 500:
        raise ValueError("Use a link of at most 500 characters.")
    return url


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


Name = _text(1, 100)
Building = _text(1, 100)
Floor = _text(1, 10)
Description = _text(1, 300)
ImageUrl = Annotated[HttpUrl, AfterValidator(_max_500_chars)]
Latitude = Annotated[float, AfterValidator(_check_latitude)]
Longitude = Annotated[float, AfterValidator(_check_longitude)]


def to_db(model: BaseModel, **dump_options) -> dict:
    """Model -> column values: snake_case keys, links as plain strings, enums as their values."""
    values = model.model_dump(by_alias=False, **dump_options)
    for key, value in values.items():
        if isinstance(value, HttpUrl):
            values[key] = str(value)
        elif isinstance(value, StrEnum):
            values[key] = value.value
    return values


def _hh_mm(value: time) -> str:
    return value.strftime("%H:%M")


# ---------------------------------------------------------------- suppliers


class SupplierCreate(RequestModel):
    name: Name
    type: SupplierType
    building: Building
    floor: Floor | None = None
    location_description: Description
    latitude: Latitude
    longitude: Longitude
    start_time: time
    end_time: time
    image_url: ImageUrl | None = None
    active: bool = True


class SupplierUpdate(RequestModel):
    """PATCH body. Only the fields sent change. null clears floor or imageUrl."""

    name: Name | None = None
    type: SupplierType | None = None
    building: Building | None = None
    floor: Floor | None = None
    location_description: Description | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    start_time: time | None = None
    end_time: time | None = None
    image_url: ImageUrl | None = None
    active: bool | None = None

    @field_validator(
        "name", "type", "building", "location_description", "latitude", "longitude",
        "start_time", "end_time", "active",
        mode="before",
    )
    @classmethod
    def required_fields_cannot_be_cleared(cls, value):
        if value is None:
            raise ValueError("This field is required and cannot be empty.")
        return value

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        return self


class SupplierOut(CamelModel):
    id: int
    name: str
    type: SupplierType
    building: str
    floor: str | None
    location_description: str
    latitude: float
    longitude: float
    start_time: time
    end_time: time
    image_url: str | None
    active: bool
    is_open_now: bool
    distance_m: float | None = Field(
        default=None, description="Metres from nearLat/nearLng; only set when those are given."
    )
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    updated_by: str | None

    @computed_field
    @property
    def location(self) -> str:
        """Short display form, e.g. "Central Library, Floor 1"."""
        return f"{self.building}, Floor {self.floor}" if self.floor else self.building

    @field_serializer("start_time", "end_time")
    def _time(self, value: time) -> str:
        return _hh_mm(value)


class Page[T](CamelModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class SupplierSort(StrEnum):
    NAME = "name"
    NAME_DESC = "-name"
    TYPE = "type"
    NEWEST = "-createdAt"
    RECENTLY_UPDATED = "-updatedAt"
    DISTANCE = "distance"


# ------------------------------------------------------- delivery locations


class DeliveryLocationCreate(RequestModel):
    name: Name
    description: Description
    latitude: Latitude
    longitude: Longitude
    active: bool = True


class DeliveryLocationUpdate(RequestModel):
    name: Name | None = None
    description: Description | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    active: bool | None = None

    @field_validator("*", mode="before")
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
    description: str
    latitude: float
    longitude: float
    active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    updated_by: str | None


# --------------------------------------------------------------------- meta


class ServedArea(CamelModel):
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float


class Meta(CamelModel):
    types: list[SupplierType]
    served_area: ServedArea
    timezone: str
