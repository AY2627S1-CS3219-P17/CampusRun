# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-assisted review and debugging for message contract for the credit service: the commands it accepts over RabbitMQ,
#        which service may send each one, and the reply it sends back.
# Author review: <to be completed by author>

"""The credit service's message contract.

Every change to a balance arrives as a command message on RabbitMQ. A command names one action for one
receiver (this service), so it is a message, not an event: see docs/credit-service-plan.md.

    exchange credit.commands (topic) --routing key--> queue credit-service.commands --> credit-worker

AMQP properties carry the envelope; the body is the JSON below (camelCase, like the HTTP APIs):

    type        command name, e.g. "ReserveCredits"
    message_id  unique per message; recorded in the ledger to trace a change back to its sender
    user_id     the sending service's RabbitMQ user. RabbitMQ refuses a publish whose user_id doesn't match the
                connection's login, so this can't be forged. The worker checks it against SENDERS below.

Replies go to exchange credit.replies with routing key = the sender's user_id, and correlation_id = the
command's message_id. OpenWallet has no reply: the wallet's status is visible at GET /wallets/me.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, PositiveInt, model_validator
from pydantic.alias_generators import to_camel

from credit_service.tables import ReservationStatus

COMMAND_EXCHANGE = "credit.commands"
COMMAND_QUEUE = "credit-service.commands"
REPLY_EXCHANGE = "credit.replies"
REPLY_TYPE = "ReservationResult"


class _Message(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, extra="forbid", frozen=True)


class OpenWallet(_Message):
    """Sent by the User Service after a user registers. Opens a wallet with the initial allocation, once."""

    user_id: PositiveInt


class ReserveCredits(_Message):
    """Sent by the Order Service when an errand is created. Holds `amount` of the requester's available credits."""

    errand_id: PositiveInt
    requester_id: PositiveInt
    amount: PositiveInt


class AdjustReservation(_Message):
    """Sent by the Order Service when the requester changes an OPEN errand's reward (F7.3.1).

    `amount` is the new reward. `revision` goes up by one with every change of that errand's reward, so a change
    that arrives after a newer one is ignored instead of undoing it.
    """

    errand_id: PositiveInt
    requester_id: PositiveInt
    amount: PositiveInt
    revision: PositiveInt


class TransferCredits(_Message):
    """Sent by the Order Service when an errand is COMPLETED. Pays the held credits to the courier."""

    errand_id: PositiveInt
    requester_id: PositiveInt
    courier_id: PositiveInt

    @model_validator(mode="after")
    def courier_is_not_requester(self) -> "TransferCredits":
        if self.courier_id == self.requester_id:
            raise ValueError("courierId must differ from requesterId")
        return self


class ReleaseCredits(_Message):
    """Sent by the Order Service when an errand is CANCELLED or EXPIRED. Returns the held credits."""

    errand_id: PositiveInt
    requester_id: PositiveInt
    reason: Literal["CANCELLED", "EXPIRED"]


Command = OpenWallet | ReserveCredits | AdjustReservation | TransferCredits | ReleaseCredits


@dataclass(frozen=True)
class CommandSpec:
    model: type[Command]
    routing_key: str
    # RabbitMQ users allowed to send it. The broker also limits which routing keys each user may publish
    # (rabbitmq/definitions.json); this check doesn't rely on that.
    senders: frozenset[str]
    replies: bool


COMMANDS: dict[str, CommandSpec] = {
    "OpenWallet": CommandSpec(OpenWallet, "wallet.open", frozenset({"user-service"}), replies=False),
    "ReserveCredits": CommandSpec(ReserveCredits, "reservation.reserve", frozenset({"order-service"}), replies=True),
    "AdjustReservation": CommandSpec(
        AdjustReservation, "reservation.adjust", frozenset({"order-service"}), replies=True
    ),
    "TransferCredits": CommandSpec(TransferCredits, "reservation.transfer", frozenset({"order-service"}), replies=True),
    "ReleaseCredits": CommandSpec(ReleaseCredits, "reservation.release", frozenset({"order-service"}), replies=True),
}

# Why a command changed nothing. Null in a reply when the command took effect, now or on an earlier delivery.
Rejection = Literal[
    "INSUFFICIENT_CREDITS",  # reserve or adjust: available balance too low
    "NO_WALLET",  # reserve: the requester has no wallet yet
    "CANCELLED_BEFORE_RESERVE",  # reserve: a release for this errand arrived first
    "NO_RESERVATION",  # adjust or transfer: nothing was ever reserved for this errand
    "NOT_HELD",  # adjust or transfer: the reservation was rejected
    "ALREADY_TRANSFERRED",  # release or adjust: the credits were already paid to the courier
    "ALREADY_RELEASED",  # transfer or adjust: the credits were already returned
    "STALE_REVISION",  # adjust: a newer reward change was already applied
    "NO_COURIER_WALLET",  # transfer: the courier has no wallet; the credits stay held, so it can be retried
    "OTHER_COURIER",  # transfer: already paid to a different courier
]


class ReservationResult(_Message):
    """The reply to every reservation command: what is true about the errand's credits now.

    It describes the current state, not just this command's effect, so a repeated or late reply can be applied
    by comparing states instead of counting messages.
    """

    errand_id: int
    # Null when there is no reservation for the errand (a transfer or adjust that arrived first)
    status: ReservationStatus | None
    amount: int
    revision: int
    courier_id: int | None
    # Why the reservation is REJECTED or RELEASED, e.g. INSUFFICIENT_CREDITS or EXPIRED
    reason: str | None
    rejection: Rejection | None
