# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated seed loader for seed/*.csv, run as a separate command after migrations.
# Author review: <to be completed by author>

"""Load the seed data into empty tables.

    uv run python -m supplier_service.seed

Run after `alembic upgrade head`. Safe to run again: a table that already has
rows (including deleted ones) is left alone.

seed/suppliers.csv keeps the column layout of the template's
data/csv/supplier-seed-data.csv so the two are easy to compare:

    Name,Type,Building,Floor,Location Description,Latitude,Longitude,
    StartingTime,ClosingTime,ImageURL

Each row goes through the same validation as an API request; a row that fails
is logged and skipped rather than stored.
"""

import asyncio
import csv
import io
import logging
import re
from datetime import time
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from supplier_service.config import get_settings
from supplier_service.db import create_engine
from supplier_service.schemas import DeliveryLocationCreate, SupplierCreate, SupplierType, to_db
from supplier_service.tables import delivery_locations, suppliers

log = logging.getLogger(__name__)

SEED_USER = "seed"
# Any fixed number; stops two seed runs started at once from both inserting
SEED_LOCK_KEY = 3219_0002

# CSV "Type" -> supplier type. "Food/Coffee" places are cafés, shown as Drinks in the web client.
CSV_TYPES = {
    "food": SupplierType.FOOD,
    "food/coffee": SupplierType.DRINKS,
    "coffee": SupplierType.DRINKS,
    "drinks": SupplierType.DRINKS,
    "shopping": SupplierType.SHOPPING,
    "printing": SupplierType.PRINTING,
}

_BLOB_URL = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/(.+)$")


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # The template CSV was saved from Excel on Windows (cp1252)
        content = raw.decode("cp1252")
    rows = csv.DictReader(io.StringIO(content))
    return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in rows]


def parse_hours(value: str) -> time:
    """'0900hrs' -> 09:00"""
    digits = value.lower().removesuffix("hrs").strip()
    return time(int(digits[:2]), int(digits[2:4]))


def raw_image_url(value: str) -> str | None:
    """A github.com/.../blob/... link shows a web page, not the image. Point at the raw file."""
    if not value:
        return None
    match = _BLOB_URL.match(value)
    if match:
        owner, repo, rest = match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"
    return value


def supplier_from_row(row: dict[str, str]) -> SupplierCreate:
    csv_type = row["Type"].lower()
    if csv_type not in CSV_TYPES:
        raise ValueError(f"unknown type {row['Type']!r}")
    return SupplierCreate(
        name=row["Name"],
        type=CSV_TYPES[csv_type],
        building=row["Building"],
        floor=row.get("Floor") or None,
        location_description=row["Location Description"],
        latitude=float(row["Latitude"]),
        longitude=float(row["Longitude"]),
        start_time=parse_hours(row["StartingTime"]),
        end_time=parse_hours(row["ClosingTime"]),
        image_url=raw_image_url(row.get("ImageURL", "")),
    )


def delivery_location_from_row(row: dict[str, str]) -> DeliveryLocationCreate:
    return DeliveryLocationCreate(
        name=row["Name"],
        description=row["Description"],
        latitude=float(row["Latitude"]),
        longitude=float(row["Longitude"]),
    )


def _load(path: Path, parse) -> list[dict]:
    if not path.exists():
        log.warning("Seed file %s not found; skipping.", path)
        return []
    values = []
    for line_no, row in enumerate(read_csv(path), start=2):
        try:
            model = parse(row)
        except (ValidationError, ValueError, KeyError) as exc:
            log.warning("Skipping %s line %d (%s): %s", path.name, line_no, row.get("Name"), exc)
            continue
        values.append(to_db(model) | {"created_by": SEED_USER, "updated_by": SEED_USER})
    return values


async def seed_if_empty(conn: AsyncConnection, seed_dir: Path) -> None:
    await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SEED_LOCK_KEY})

    if await conn.scalar(select(func.count()).select_from(suppliers)) == 0:
        rows = _load(seed_dir / "suppliers.csv", supplier_from_row)
        if rows:
            await conn.execute(insert(suppliers), rows)
        log.info("Seeded %d suppliers.", len(rows))
    else:
        log.info("Suppliers table already has data; not seeding it.")

    if await conn.scalar(select(func.count()).select_from(delivery_locations)) == 0:
        rows = _load(seed_dir / "delivery-locations.csv", delivery_location_from_row)
        if rows:
            await conn.execute(insert(delivery_locations), rows)
        log.info("Seeded %d delivery locations.", len(rows))
    else:
        log.info("Delivery locations table already has data; not seeding it.")


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with engine.begin() as conn:
            await seed_if_empty(conn, settings.seed_dir)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(main())
