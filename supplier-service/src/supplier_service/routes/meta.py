# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated endpoint returning supplier types and the served area for forms and filters.
# Author review: <to be completed by author>

from fastapi import APIRouter

from supplier_service.auth import AnyUser
from supplier_service.config import get_settings
from supplier_service.schemas import Meta, ServedArea, SupplierType

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta, summary="Supplier types and served area, for forms and filters")
async def meta(user: AnyUser):
    s = get_settings()
    return Meta(
        types=list(SupplierType),
        served_area=ServedArea(
            min_lat=s.served_area_min_lat,
            max_lat=s.served_area_max_lat,
            min_lng=s.served_area_min_lng,
            max_lng=s.served_area_max_lng,
        ),
        timezone=s.timezone,
    )
