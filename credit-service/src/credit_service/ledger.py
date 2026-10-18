# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for wallet operations (open, reserve, adjust, transfer, release): each is atomic, idempotent
#        and writes a ledger entry for every balance change.
# Author review: <to be completed by author>

"""The only code that changes balances. The worker calls apply() inside one database transaction per message.

Three rules keep the credit economy consistent:

1. Atomic: every function runs inside the caller's transaction, so the wallet rows, the reservation and the ledger
   entries are all committed together or not at all (N5.1.1).
2. Idempotent by business key: wallets are keyed by user id and reservations by errand id, and a reservation only
   moves forward from HELD. Applying the same command twice finds the first result and changes nothing (N5.1.2).
3. Checked by Postgres: the balance check is part of the UPDATE (`... WHERE available >= amount`), so no other
   transaction can spend the same credits between the check and the debit. CHECK constraints reject anything
   that would make a balance negative, even if this code had a bug.

Locks are always taken in the same order (the reservation row, then wallets by ascending user id), so two
transactions never wait on each other in a cycle.
"""

from sqlalchemy import Row, exists, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from credit_service.commands import (
    AdjustReservation,
    Command,
    OpenWallet,
    Rejection,
    ReleaseCredits,
    ReservationResult,
    ReserveCredits,
    TransferCredits,
)
from credit_service.tables import EntryKind, ReservationStatus, ledger_entries, reservations, wallets

HELD = ReservationStatus.HELD
TRANSFERRED = ReservationStatus.TRANSFERRED
RELEASED = ReservationStatus.RELEASED
REJECTED = ReservationStatus.REJECTED


class InvalidCommand(Exception):
    """The command contradicts what this service already knows, e.g. another requester for the same errand.

    That is a bug in the sender, so the worker dead-letters the message for a person to look at instead of guessing.
    """


async def apply(
    conn: AsyncConnection, command: Command, *, message_id: str | None, initial_credits: int
) -> ReservationResult | bool:
    match command:
        case OpenWallet():
            return await open_wallet(conn, command, initial_credits=initial_credits, message_id=message_id)
        case ReserveCredits():
            return await reserve(conn, command, message_id=message_id)
        case AdjustReservation():
            return await adjust(conn, command, message_id=message_id)
        case TransferCredits():
            return await transfer(conn, command, message_id=message_id)
        case ReleaseCredits():
            return await release(conn, command, message_id=message_id)


# ------------------------------------------------------------------ wallets


async def open_wallet(
    conn: AsyncConnection, command: OpenWallet, *, initial_credits: int, message_id: str | None = None
) -> bool:
    """Creates the wallet with the initial allocation. Returns False if it already existed (a repeat)."""
    # The primary key on user_id makes a second wallet impossible; ON CONFLICT turns a repeat into a no-op,
    # and the allocation is only written when this insert actually created the row.
    balances = (
        await conn.execute(
            pg_insert(wallets)
            .values(user_id=command.user_id, available=initial_credits, reserved=0)
            .on_conflict_do_nothing(index_elements=[wallets.c.user_id])
            .returning(wallets.c.available, wallets.c.reserved)
        )
    ).one_or_none()
    if balances is None:
        return False
    await _record(conn, command.user_id, None, EntryKind.INITIAL_ALLOCATION, initial_credits, 0, balances, message_id)
    return True


# ------------------------------------------------------------------ reservations


async def reserve(conn: AsyncConnection, command: ReserveCredits, *, message_id: str | None = None) -> ReservationResult:
    """Moves `amount` from the requester's available to reserved balance, once per errand."""
    # 1. Claim the errand first. A concurrent copy of this message waits on the unique key, then finds this row.
    claimed = await conn.scalar(
        pg_insert(reservations)
        .values(
            errand_id=command.errand_id,
            requester_id=command.requester_id,
            amount=command.amount,
            status=HELD,
        )
        .on_conflict_do_nothing(index_elements=[reservations.c.errand_id])
        .returning(reservations.c.errand_id)
    )
    if claimed is None:
        existing = await _load(conn, command.errand_id)
        assert existing is not None
        _check_requester(existing, command.requester_id)
        # A repeat: report what happened the first time
        return _result(existing, existing.reason if existing.status == REJECTED else None)

    # 2. Check and debit in one statement: only updates if the credits are there right now
    balances = await _move(
        conn, command.requester_id, -command.amount, command.amount, require_available=command.amount
    )
    if balances is None:
        has_wallet = await conn.scalar(select(exists().where(wallets.c.user_id == command.requester_id)))
        reason: Rejection = "INSUFFICIENT_CREDITS" if has_wallet else "NO_WALLET"
        # Kept as REJECTED rather than deleted, so a repeat of this message gets the same answer even if the
        # balance has changed since (the Order Service already told the requester it failed)
        row = await _update_reservation(conn, command.errand_id, status=REJECTED, reason=reason)
        return _result(row, reason)

    # 3. Record the movement, all in the same transaction
    await _record(
        conn, command.requester_id, command.errand_id, EntryKind.RESERVE, -command.amount, command.amount,
        balances, message_id,
    )
    return _result(await _load(conn, command.errand_id))


async def adjust(conn: AsyncConnection, command: AdjustReservation, *, message_id: str | None = None) -> ReservationResult:
    """Changes the credits held for an errand whose reward was amended (F7.3.1)."""
    row = await _load(conn, command.errand_id)
    if row is None:
        return _missing(command.errand_id)
    _check_requester(row, command.requester_id)
    if row.status != HELD:
        return _result(row, _not_held(row))
    if command.revision <= row.revision:
        # A repeat, or older than a change already applied: leave the hold as it is
        return _result(row, None if row.amount == command.amount else "STALE_REVISION")

    change = command.amount - row.amount
    if change > 0:
        balances = await _move(conn, row.requester_id, -change, change, require_available=change)
        if balances is None:
            # Still record the revision, so a repeat of this message is refused the same way
            row = await _update_reservation(conn, row.errand_id, revision=command.revision)
            return _result(row, "INSUFFICIENT_CREDITS")
        await _record(conn, row.requester_id, row.errand_id, EntryKind.RESERVE, -change, change, balances, message_id)
    elif change < 0:
        balances = _must(await _move(conn, row.requester_id, -change, change))
        await _record(conn, row.requester_id, row.errand_id, EntryKind.RELEASE, -change, change, balances, message_id)

    row = await _update_reservation(conn, row.errand_id, amount=command.amount, revision=command.revision)
    return _result(row)


async def transfer(conn: AsyncConnection, command: TransferCredits, *, message_id: str | None = None) -> ReservationResult:
    """Pays the held credits to the courier: one indivisible change to both wallets (F13.1.1)."""
    row = await _load(conn, command.errand_id)
    if row is None:
        return _missing(command.errand_id)
    _check_requester(row, command.requester_id)
    if row.status == TRANSFERRED:
        return _result(row, None if row.courier_id == command.courier_id else "OTHER_COURIER")
    if row.status != HELD:
        return _result(row, _not_held(row))

    # Lock both wallets in user id order, so two transfers between the same two users can't deadlock
    locked = set(
        await conn.scalars(
            select(wallets.c.user_id)
            .where(wallets.c.user_id.in_([row.requester_id, command.courier_id]))
            .order_by(wallets.c.user_id)
            .with_for_update()
        )
    )
    if command.courier_id not in locked:
        # Leave the credits held; the Order Service can send the transfer again once the wallet exists
        return _result(row, "NO_COURIER_WALLET")

    paid = _must(await _move(conn, row.requester_id, 0, -row.amount))
    await _record(conn, row.requester_id, row.errand_id, EntryKind.TRANSFER_OUT, 0, -row.amount, paid, message_id)
    received = _must(await _move(conn, command.courier_id, row.amount, 0))
    await _record(conn, command.courier_id, row.errand_id, EntryKind.TRANSFER_IN, row.amount, 0, received, message_id)

    row = await _update_reservation(conn, row.errand_id, status=TRANSFERRED, courier_id=command.courier_id)
    return _result(row)


async def release(conn: AsyncConnection, command: ReleaseCredits, *, message_id: str | None = None) -> ReservationResult:
    """Returns the held credits to the requester when the errand is cancelled or expires (F13.2.1)."""
    row = await _load(conn, command.errand_id)
    if row is None:
        # The release overtook its reserve. Leave a REJECTED placeholder so the reserve, when it arrives,
        # holds nothing instead of locking the credits of an errand that has already ended (N7.1.1).
        placed = await conn.scalar(
            pg_insert(reservations)
            .values(
                errand_id=command.errand_id,
                requester_id=command.requester_id,
                amount=0,
                status=REJECTED,
                reason="CANCELLED_BEFORE_RESERVE",
            )
            .on_conflict_do_nothing(index_elements=[reservations.c.errand_id])
            .returning(reservations.c.errand_id)
        )
        row = await _load(conn, command.errand_id)
        assert row is not None
        if placed is not None:
            return _result(row)
        # Otherwise a reserve committed in between; carry on with it below

    _check_requester(row, command.requester_id)
    if row.status in (RELEASED, REJECTED):
        return _result(row)
    if row.status == TRANSFERRED:
        return _result(row, "ALREADY_TRANSFERRED")

    balances = _must(await _move(conn, row.requester_id, row.amount, -row.amount))
    await _record(conn, row.requester_id, row.errand_id, EntryKind.RELEASE, row.amount, -row.amount, balances, message_id)
    row = await _update_reservation(conn, row.errand_id, status=RELEASED, reason=command.reason)
    return _result(row)


# ------------------------------------------------------------------ helpers


async def _load(conn: AsyncConnection, errand_id: int) -> Row | None:
    # FOR UPDATE: another transaction changing this reservation waits until this one commits, then re-reads it
    return (
        await conn.execute(select(reservations).where(reservations.c.errand_id == errand_id).with_for_update())
    ).one_or_none()


async def _update_reservation(conn: AsyncConnection, errand_id: int, **values) -> Row:
    return (
        await conn.execute(
            update(reservations).where(reservations.c.errand_id == errand_id).values(**values).returning(reservations)
        )
    ).one()


async def _move(
    conn: AsyncConnection,
    user_id: int,
    available_delta: int,
    reserved_delta: int,
    *,
    require_available: int | None = None,
) -> Row | None:
    """Changes one wallet's balances in a single UPDATE. Returns the new balances, or None if nothing changed."""
    statement = (
        update(wallets)
        .where(wallets.c.user_id == user_id)
        .values(available=wallets.c.available + available_delta, reserved=wallets.c.reserved + reserved_delta)
        .returning(wallets.c.available, wallets.c.reserved)
    )
    if require_available is not None:
        statement = statement.where(wallets.c.available >= require_available)
    return (await conn.execute(statement)).one_or_none()


def _must(balances: Row | None) -> Row:
    # A HELD reservation implies its wallets exist; if not, the data is inconsistent and the worker must stop on it
    if balances is None:
        raise RuntimeError("A wallet behind a held reservation is missing")
    return balances


async def _record(
    conn: AsyncConnection,
    user_id: int,
    errand_id: int | None,
    kind: EntryKind,
    available_delta: int,
    reserved_delta: int,
    balances: Row,
    message_id: str | None,
) -> None:
    await conn.execute(
        insert(ledger_entries).values(
            user_id=user_id,
            errand_id=errand_id,
            kind=kind,
            available_delta=available_delta,
            reserved_delta=reserved_delta,
            available_after=balances.available,
            reserved_after=balances.reserved,
            message_id=message_id,
        )
    )


def _check_requester(row: Row, requester_id: int) -> None:
    if row.requester_id != requester_id:
        raise InvalidCommand(
            f"errand {row.errand_id} belongs to requester {row.requester_id}, but the message says {requester_id}"
        )


def _not_held(row: Row) -> Rejection:
    match row.status:
        case ReservationStatus.TRANSFERRED:
            return "ALREADY_TRANSFERRED"
        case ReservationStatus.RELEASED:
            return "ALREADY_RELEASED"
        case _:
            return "NOT_HELD"


def _missing(errand_id: int) -> ReservationResult:
    return ReservationResult(
        errand_id=errand_id,
        status=None,
        amount=0,
        revision=0,
        courier_id=None,
        reason=None,
        rejection="NO_RESERVATION",
    )


def _result(row: Row, rejection: Rejection | None = None) -> ReservationResult:
    return ReservationResult(
        errand_id=row.errand_id,
        status=ReservationStatus(row.status),
        amount=row.amount,
        revision=row.revision,
        courier_id=row.courier_id,
        reason=row.reason,
        rejection=rejection,
    )
