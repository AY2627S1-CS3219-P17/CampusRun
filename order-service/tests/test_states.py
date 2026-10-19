# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated tests for the rule that maps an errand's state to where its credits should end up.
# Author review: <to be completed by author>

import pytest

from order_service.states import FINISHED, UNFINISHED, CreditStatus, State, target_credit_status


@pytest.mark.parametrize("state", [State.OPEN, State.ACCEPTED, State.PICKED_UP, State.DELIVERED])
def test_credits_stay_held_until_the_errand_ends(state: State) -> None:
    assert target_credit_status(state) == {CreditStatus.HELD}


def test_a_completed_errand_pays_the_courier() -> None:
    assert target_credit_status(State.COMPLETED) == {CreditStatus.TRANSFERRED}


@pytest.mark.parametrize("state", [State.CANCELLED, State.EXPIRED])
def test_an_ended_errand_returns_the_credits_or_never_held_any(state: State) -> None:
    assert target_credit_status(state) == {CreditStatus.RELEASED, CreditStatus.REJECTED}


def test_pending_is_never_a_target() -> None:
    # PENDING only means a reply hasn't arrived yet, so no state should stay there
    assert all(CreditStatus.PENDING not in target_credit_status(s) for s in State)


def test_every_state_is_either_unfinished_or_finished() -> None:
    assert UNFINISHED | FINISHED == set(State)
    assert not UNFINISHED & FINISHED
