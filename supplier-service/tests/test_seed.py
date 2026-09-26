# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-assisted review for tests for the seed loader and the seed data.
# Author review: <to be completed by author>

from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import func, select

from supplier_service.config import get_settings
from supplier_service.seed import parse_hours, raw_image_url, read_csv, seed_if_empty, supplier_from_row
from supplier_service.tables import delivery_locations, suppliers

pytestmark = pytest.mark.anyio

TEMPLATE_CSV = Path(__file__).resolve().parents[2] / "data" / "csv" / "supplier-seed-data.csv"


def test_parse_helpers():
    assert parse_hours("0900hrs") == time(9, 0)
    assert parse_hours("2359hrs") == time(23, 59)
    assert raw_image_url("") is None
    assert raw_image_url(
        "https://github.com/CS3219-AY2627S1/FoC-Template/blob/main/data/images/ANNA.jpeg"
    ) == "https://raw.githubusercontent.com/CS3219-AY2627S1/FoC-Template/main/data/images/ANNA.jpeg"


def test_every_seed_row_is_valid():
    rows = read_csv(get_settings().seed_dir / "suppliers.csv")
    assert len(rows) >= 21
    parsed = {r["Name"]: supplier_from_row(r) for r in rows}
    assert {p.type for p in parsed.values()} == {"Food", "Drinks", "Shopping", "Printing"}
    assert parsed["TOMORO COFFEE"].type == "Drinks"  # "Food/Coffee" in the CSV


def test_unknown_type_is_rejected():
    row = read_csv(get_settings().seed_dir / "suppliers.csv")[0] | {"Type": "Laundry"}
    with pytest.raises(ValueError):
        supplier_from_row(row)


@pytest.mark.skipif(not TEMPLATE_CSV.exists(), reason="template CSV not in this checkout")
def test_template_csv_still_readable():
    rows = read_csv(TEMPLATE_CSV)  # cp1252, from the template repo
    assert rows[0]["Name"] == "Anna's x Soup Union"


async def test_seed_runs_once(engine):
    seed_dir = get_settings().seed_dir
    async with engine.begin() as conn:
        await seed_if_empty(conn, seed_dir)
        await seed_if_empty(conn, seed_dir)
        count = await conn.scalar(select(func.count()).select_from(suppliers))
        points = await conn.scalar(select(func.count()).select_from(delivery_locations))
    assert count == len(read_csv(seed_dir / "suppliers.csv"))
    assert points > 0
