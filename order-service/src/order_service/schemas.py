# AI Assistance Disclosure:
# Tool: OpenAI Codex (GPT-6), date: 2026-10-17
# Scope: Defined partial autofill contracts and a strict model schema with delivery-only location details and nullable string credits.
# Author review: <to be completed by author>

from pydantic import BaseModel, ConfigDict, field_validator


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