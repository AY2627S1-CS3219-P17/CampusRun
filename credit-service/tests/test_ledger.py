# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review for tests for wallet operations: atomicity, idempotency, ordering, concurrency and the
#        database constraints behind them.
# Author review: <to be completed by author>

import asyncio

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from credit_service import ledger
from credit_service.audit import run_audit
from credit_service.commands import AdjustReservation, OpenWallet, ReleaseCredits, ReserveCredits, TransferCredits
from credit_service.tables import ledger_entries, reservations, wallets

pytestmark = pytest.mark.anyio

REQUESTER, COURIER, OTHER = 1, 2, 3


async def run(engine, op, command):
    async with engine.begin() as conn:
        if isinstance(command, OpenWallet):
            return await ledger.open_wallet(conn, command, initial_credits=100)
        return await op(conn, command)


async def open_wallets(engine, *user_ids):
    for user_id in user_ids:
        assert await run(engine, None, OpenWallet(user_id=user_id))


async def balances(engine, user_id) -> tuple[int, int] | None:
    async with engine.connect() as conn:
        row = (await conn.execute(select(wallets.c.available, wallets.c.reserved).where(wallets.c.user_id == user_id))).one_or_none()
    return tuple(row) if row else None


async def entries(engine, **where) -> list:
    async with engine.connect() as conn:
        query = select(ledger_entries).order_by(ledger_entries.c.id)
        for column, value in where.items():
            query = query.where(ledger_entries.c[column] == value)
        return list(await conn.execute(query))


async def assert_consistent(engine):
    async with engine.connect() as conn:
        report = await run_audit(conn, stale_hold_hours=48)
    assert report.ok, report.problems
    return report


def reserve_cmd(errand_id=10, amount=15, requester=REQUESTER):
    return ReserveCredits(errand_id=errand_id, requester_id=requester, amount=amount)


# ------------------------------------------------------------------ opening wallets


async def test_open_wallet_grants_the_initial_allocation_once(engine):
    assert await run(engine, None, OpenWallet(user_id=REQUESTER)) is True
    assert await run(engine, None, OpenWallet(user_id=REQUESTER)) is False
    assert await balances(engine, REQUESTER) == (100, 0)
    allocations = await entries(engine, user_id=REQUESTER)
    assert [(e.kind, e.available_delta) for e in allocations] == [("INITIAL_ALLOCATION", 100)]
    await assert_consistent(engine)


async def test_concurrent_open_wallet_messages_allocate_once(engine):
    results = await asyncio.gather(*(run(engine, None, OpenWallet(user_id=REQUESTER)) for _ in range(20)))
    assert results.count(True) == 1
    assert await balances(engine, REQUESTER) == (100, 0)
    assert len(await entries(engine, user_id=REQUESTER)) == 1


async def test_database_refuses_a_second_allocation_even_without_the_code(engine):
    await open_wallets(engine, REQUESTER)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                ledger_entries.insert().values(
                    user_id=REQUESTER, kind="INITIAL_ALLOCATION", available_delta=100, reserved_delta=0,
                    available_after=200, reserved_after=0,
                )
            )


async def test_database_refuses_a_negative_balance(engine):
    await open_wallets(engine, REQUESTER)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(update(wallets).where(wallets.c.user_id == REQUESTER).values(available=-1))


async def test_total_is_computed_by_the_database(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(amount=30))
    async with engine.connect() as conn:
        row = (await conn.execute(select(wallets.c.available, wallets.c.reserved, wallets.c.total))).one()
    assert tuple(row) == (70, 30, 100)


# ------------------------------------------------------------------ reserve


async def test_reserve_moves_available_to_reserved(engine):
    await open_wallets(engine, REQUESTER)
    result = await run(engine, ledger.reserve, reserve_cmd(amount=15))
    assert (result.status, result.amount, result.rejection) == ("HELD", 15, None)
    assert await balances(engine, REQUESTER) == (85, 15)
    [entry] = await entries(engine, errand_id=10)
    assert (entry.kind, entry.available_delta, entry.reserved_delta, entry.available_after, entry.reserved_after) == (
        "RESERVE", -15, 15, 85, 15,
    )
    await assert_consistent(engine)


async def test_repeated_reserve_holds_once(engine):
    await open_wallets(engine, REQUESTER)
    first = await run(engine, ledger.reserve, reserve_cmd())
    again = await run(engine, ledger.reserve, reserve_cmd())
    assert first == again
    assert await balances(engine, REQUESTER) == (85, 15)
    assert len(await entries(engine, errand_id=10)) == 1


async def test_reserve_rejects_more_than_the_available_balance(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(errand_id=10, amount=90))
    result = await run(engine, ledger.reserve, reserve_cmd(errand_id=11, amount=20))
    assert (result.status, result.rejection, result.reason) == ("REJECTED", "INSUFFICIENT_CREDITS", "INSUFFICIENT_CREDITS")
    assert await balances(engine, REQUESTER) == (10, 90)
    assert await entries(engine, errand_id=11) == []


async def test_a_rejected_reserve_stays_rejected_when_repeated_later(engine):
    # The Order Service already told the requester it failed, so a redelivery must not hold credits after all
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd(errand_id=10, amount=90))
    await run(engine, ledger.reserve, reserve_cmd(errand_id=11, amount=20))
    await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="CANCELLED"))
    again = await run(engine, ledger.reserve, reserve_cmd(errand_id=11, amount=20))
    assert (again.status, again.rejection) == ("REJECTED", "INSUFFICIENT_CREDITS")
    assert await balances(engine, REQUESTER) == (100, 0)


async def test_reserve_without_a_wallet_is_rejected(engine):
    result = await run(engine, ledger.reserve, reserve_cmd())
    assert (result.status, result.rejection) == ("REJECTED", "NO_WALLET")


async def test_reserve_for_an_errand_of_another_requester_is_invalid(engine):
    await open_wallets(engine, REQUESTER, OTHER)
    await run(engine, ledger.reserve, reserve_cmd())
    with pytest.raises(ledger.InvalidCommand):
        await run(engine, ledger.reserve, reserve_cmd(requester=OTHER))


async def test_concurrent_reserves_never_overspend(engine):
    await open_wallets(engine, REQUESTER)
    results = await asyncio.gather(
        *(run(engine, ledger.reserve, reserve_cmd(errand_id=100 + i, amount=7)) for i in range(40))
    )
    held = [r for r in results if r.status == "HELD"]
    assert len(held) == 100 // 7
    assert all(r.rejection == "INSUFFICIENT_CREDITS" for r in results if r.status == "REJECTED")
    assert await balances(engine, REQUESTER) == (100 % 7, 7 * (100 // 7))
    await assert_consistent(engine)


# ------------------------------------------------------------------ transfer


async def test_transfer_pays_the_courier(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    result = await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER))
    assert (result.status, result.courier_id, result.rejection) == ("TRANSFERRED", COURIER, None)
    assert await balances(engine, REQUESTER) == (85, 0)
    assert await balances(engine, COURIER) == (115, 0)
    kinds = [(e.user_id, e.kind, e.available_delta, e.reserved_delta) for e in await entries(engine, errand_id=10)]
    assert kinds == [
        (REQUESTER, "RESERVE", -15, 15),
        (REQUESTER, "TRANSFER_OUT", 0, -15),
        (COURIER, "TRANSFER_IN", 15, 0),
    ]
    report = await assert_consistent(engine)
    assert report.total_in_circulation == report.total_allocated == 200


async def test_repeated_transfer_pays_once(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    transfer = TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER)
    first = await run(engine, ledger.transfer, transfer)
    again = await run(engine, ledger.transfer, transfer)
    assert first == again
    assert await balances(engine, COURIER) == (115, 0)


async def test_concurrent_transfers_of_one_errand_pay_once(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    transfer = TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER)
    results = await asyncio.gather(*(run(engine, ledger.transfer, transfer) for _ in range(30)))
    assert {r.status for r in results} == {"TRANSFERRED"}
    assert await balances(engine, COURIER) == (115, 0)
    assert len(await entries(engine, errand_id=10, kind="TRANSFER_IN")) == 1
    await assert_consistent(engine)


async def test_transfer_to_another_courier_after_paying_is_refused(engine):
    await open_wallets(engine, REQUESTER, COURIER, OTHER)
    await run(engine, ledger.reserve, reserve_cmd())
    await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER))
    result = await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=OTHER))
    assert (result.courier_id, result.rejection) == (COURIER, "OTHER_COURIER")
    assert await balances(engine, OTHER) == (100, 0)


async def test_transfer_waits_for_a_missing_courier_wallet(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd())
    transfer = TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER)
    result = await run(engine, ledger.transfer, transfer)
    assert (result.status, result.rejection) == ("HELD", "NO_COURIER_WALLET")
    assert await balances(engine, REQUESTER) == (85, 15)
    # Once the wallet exists, sending the same transfer again succeeds
    await open_wallets(engine, COURIER)
    assert (await run(engine, ledger.transfer, transfer)).status == "TRANSFERRED"


async def test_transfer_without_a_reservation(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    result = await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER))
    assert (result.status, result.rejection) == (None, "NO_RESERVATION")
    async with engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(reservations)) == 0


async def test_cross_transfers_between_two_users_do_not_deadlock(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    for i in range(20):
        requester, courier = (REQUESTER, COURIER) if i % 2 == 0 else (COURIER, REQUESTER)
        await run(engine, ledger.reserve, reserve_cmd(errand_id=200 + i, amount=1, requester=requester))
    await asyncio.gather(
        *(
            run(
                engine,
                ledger.transfer,
                TransferCredits(
                    errand_id=200 + i,
                    requester_id=REQUESTER if i % 2 == 0 else COURIER,
                    courier_id=COURIER if i % 2 == 0 else REQUESTER,
                ),
            )
            for i in range(20)
        )
    )
    assert await balances(engine, REQUESTER) == (100, 0)
    assert await balances(engine, COURIER) == (100, 0)
    await assert_consistent(engine)


# ------------------------------------------------------------------ release


async def test_release_returns_the_credits(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    result = await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="EXPIRED"))
    assert (result.status, result.reason, result.rejection) == ("RELEASED", "EXPIRED", None)
    assert await balances(engine, REQUESTER) == (100, 0)
    again = await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="EXPIRED"))
    assert again == result
    assert len(await entries(engine, errand_id=10, kind="RELEASE")) == 1
    await assert_consistent(engine)


async def test_release_after_transfer_is_refused(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd())
    await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER))
    result = await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="CANCELLED"))
    assert (result.status, result.rejection) == ("TRANSFERRED", "ALREADY_TRANSFERRED")
    assert await balances(engine, REQUESTER) == (85, 0)


async def test_transfer_after_release_is_refused(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd())
    await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="CANCELLED"))
    result = await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER))
    assert (result.status, result.rejection) == ("RELEASED", "ALREADY_RELEASED")
    assert await balances(engine, COURIER) == (100, 0)


async def test_racing_transfer_and_release_settle_exactly_once(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    for errand_id in range(300, 320):
        await run(engine, ledger.reserve, reserve_cmd(errand_id=errand_id, amount=2))
    results = await asyncio.gather(
        *(
            op
            for errand_id in range(300, 320)
            for op in (
                run(engine, ledger.transfer, TransferCredits(errand_id=errand_id, requester_id=REQUESTER, courier_id=COURIER)),
                run(engine, ledger.release, ReleaseCredits(errand_id=errand_id, requester_id=REQUESTER, reason="CANCELLED")),
            )
        )
    )
    async with engine.connect() as conn:
        statuses = list(await conn.scalars(select(reservations.c.status)))
    assert set(statuses) <= {"TRANSFERRED", "RELEASED"} and len(statuses) == 20
    paid = statuses.count("TRANSFERRED") * 2
    assert await balances(engine, COURIER) == (100 + paid, 0)
    assert await balances(engine, REQUESTER) == (100 - paid, 0)
    assert len(results) == 40
    await assert_consistent(engine)


async def test_release_that_overtakes_its_reserve_cancels_it(engine):
    await open_wallets(engine, REQUESTER)
    early = await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="CANCELLED"))
    assert (early.status, early.reason, early.rejection) == ("REJECTED", "CANCELLED_BEFORE_RESERVE", None)
    late = await run(engine, ledger.reserve, reserve_cmd(amount=15))
    assert (late.status, late.rejection) == ("REJECTED", "CANCELLED_BEFORE_RESERVE")
    assert await balances(engine, REQUESTER) == (100, 0)
    await assert_consistent(engine)


# ------------------------------------------------------------------ adjust


def adjust_cmd(amount, revision, errand_id=10):
    return AdjustReservation(errand_id=errand_id, requester_id=REQUESTER, amount=amount, revision=revision)


async def test_adjust_raises_and_lowers_the_hold(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    up = await run(engine, ledger.adjust, adjust_cmd(25, 1))
    assert (up.amount, up.revision, up.rejection) == (25, 1, None)
    assert await balances(engine, REQUESTER) == (75, 25)
    down = await run(engine, ledger.adjust, adjust_cmd(5, 2))
    assert (down.amount, down.rejection) == (5, None)
    assert await balances(engine, REQUESTER) == (95, 5)
    await assert_consistent(engine)


async def test_adjust_beyond_the_balance_keeps_the_old_hold(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    result = await run(engine, ledger.adjust, adjust_cmd(150, 1))
    assert (result.amount, result.rejection) == (15, "INSUFFICIENT_CREDITS")
    assert await balances(engine, REQUESTER) == (85, 15)
    # A repeat of the refused change is still refused
    again = await run(engine, ledger.adjust, adjust_cmd(150, 1))
    assert again.amount == 15 and again.rejection is not None


async def test_an_older_adjustment_arriving_late_is_ignored(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    await run(engine, ledger.adjust, adjust_cmd(30, 2))
    late = await run(engine, ledger.adjust, adjust_cmd(20, 1))
    assert (late.amount, late.revision, late.rejection) == (30, 2, "STALE_REVISION")
    assert await balances(engine, REQUESTER) == (70, 30)
    repeat = await run(engine, ledger.adjust, adjust_cmd(30, 2))
    assert repeat.rejection is None


async def test_adjust_after_the_errand_ended(engine):
    await open_wallets(engine, REQUESTER)
    assert (await run(engine, ledger.adjust, adjust_cmd(30, 1))).rejection == "NO_RESERVATION"
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    await run(engine, ledger.release, ReleaseCredits(errand_id=10, requester_id=REQUESTER, reason="EXPIRED"))
    result = await run(engine, ledger.adjust, adjust_cmd(30, 1))
    assert (result.status, result.rejection) == ("RELEASED", "ALREADY_RELEASED")
    assert await balances(engine, REQUESTER) == (100, 0)


async def test_the_transfer_pays_the_adjusted_amount(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    await run(engine, ledger.adjust, adjust_cmd(40, 1))
    await run(engine, ledger.transfer, TransferCredits(errand_id=10, requester_id=REQUESTER, courier_id=COURIER))
    assert await balances(engine, REQUESTER) == (60, 0)
    assert await balances(engine, COURIER) == (140, 0)
    await assert_consistent(engine)


# ------------------------------------------------------------------ audit


async def test_audit_reports_a_balance_changed_outside_the_ledger(engine):
    await open_wallets(engine, REQUESTER, COURIER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE wallets SET available = available + 50 WHERE user_id = :u"), {"u": COURIER})
    async with engine.connect() as conn:
        report = await run_audit(conn, stale_hold_hours=48)
    assert not report.ok
    assert any(f"Wallet {COURIER}" in p for p in report.problems)
    assert any("in circulation" in p for p in report.problems)


async def test_audit_lists_holds_that_waited_too_long(engine):
    await open_wallets(engine, REQUESTER)
    await run(engine, ledger.reserve, reserve_cmd(amount=15))
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE reservations SET created_at = now() - interval '3 days'"))
    async with engine.connect() as conn:
        report = await run_audit(conn, stale_hold_hours=48)
    assert report.ok
    assert [(h.errand_id, h.amount) for h in report.stale_holds] == [(10, 15)]
