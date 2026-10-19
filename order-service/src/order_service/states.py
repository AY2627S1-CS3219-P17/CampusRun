# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated errand states, credit statuses, cancel reasons and the rule for where an errand's credits
#        should end up (docs/order-service-plan.md, sections 5 and 6).
# Author review: <to be completed by author>

"""An errand is described by two values:

    state          where the errand is in its lifecycle (the glossary's errand states)
    credit_status  where its credits are in the Credit Service, which changes asynchronously

credit_status is PENDING while a credit command is on its way and its reply hasn't been applied. So an OPEN errand
with PENDING credits isn't visible to couriers yet, and a COMPLETED errand with PENDING credits hasn't paid the
courier yet.
"""

from enum import StrEnum


class State(StrEnum):
    OPEN = "OPEN"  # awaiting a courier
    ACCEPTED = "ACCEPTED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"  # the courier has reported delivery
    COMPLETED = "COMPLETED"  # the requester has confirmed
    CANCELLED = "CANCELLED"  # by the requester while OPEN, or because the credits couldn't be reserved
    EXPIRED = "EXPIRED"  # not delivered by the deadline, or not confirmed by the end of the grace period after it


class CreditStatus(StrEnum):
    PENDING = "PENDING"  # a credit command has been sent and its reply hasn't been applied yet
    HELD = "HELD"  # the reward is reserved from the requester's balance
    REJECTED = "REJECTED"  # nothing was ever reserved (not enough credits, or cancelled before the reserve)
    TRANSFERRED = "TRANSFERRED"  # paid to the courier
    RELEASED = "RELEASED"  # returned to the requester


class CancelReason(StrEnum):
    REQUESTER = "REQUESTER"
    # From the Credit Service's reply when the reserve was refused
    INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
    NO_WALLET = "NO_WALLET"


# Errands a courier can be working on; their credits stay HELD until the errand ends
IN_PROGRESS = frozenset({State.ACCEPTED, State.PICKED_UP, State.DELIVERED})
# The sweeper expires these: at the deadline, or for DELIVERED ones, once the grace period after it has passed
UNFINISHED = frozenset({State.OPEN} | IN_PROGRESS)
FINISHED = frozenset({State.COMPLETED, State.CANCELLED, State.EXPIRED})
assert UNFINISHED | FINISHED == set(State) and not UNFINISHED & FINISHED


def target_credit_status(state: State) -> frozenset[CreditStatus]:
    """Where an errand's credits should end up, given only its state.

    A reply is applied only if it reaches this target, and the reconciler resends the command for any errand whose
    credits haven't reached it, so duplicate or out-of-order replies can never move credits the wrong way.
    """
    if state in UNFINISHED:
        return frozenset({CreditStatus.HELD})
    if state is State.COMPLETED:
        return frozenset({CreditStatus.TRANSFERRED})
    # CANCELLED or EXPIRED: the reserved credits are returned, or nothing was reserved in the first place
    return frozenset({CreditStatus.RELEASED, CreditStatus.REJECTED})
