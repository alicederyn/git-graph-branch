from collections.abc import Iterator

import pytest

from git_graph_branch.github import store
from git_graph_branch.github.store import PushState, assumes_no_pr, read_push_state
from git_graph_branch.nix.fact import (
    Fact,
    release_moot_facts,
    report_calculation,
    session,
)

ABSENT, PUSHED, PRESENT = PushState.ABSENT, PushState.PUSHED, PushState.PRESENT


@pytest.fixture(autouse=True)
def watching() -> Iterator[None]:
    with session(None):
        yield


def reports(*calculations: tuple[bool, ...]) -> list[list[PushState]]:
    """Read the record in each report, with whether the remote-tracking branch
    exists, as the watch loop does: each change nixes the last report, and moot
    facts are released when a report is complete."""
    states = []
    report: Fact | None = None
    for reads in calculations:
        if report is not None:
            report.nix()
        with report_calculation() as report:
            states.append([read_push_state("key", exists) for exists in reads])
        release_moot_facts()
    return states


@pytest.mark.parametrize(
    "calculations, states",
    [
        (((False,), (True, True, True)), [[ABSENT], [PUSHED, PUSHED, PUSHED]]),
        (((True,), (True,)), [[PRESENT], [PRESENT]]),
        (((True,), (False,), (True,)), [[PRESENT], [ABSENT], [PUSHED]]),
    ],
    ids=["first push", "already pushed", "pushed again after a prune"],
)
def test_push_state(
    calculations: tuple[tuple[bool, ...], ...], states: list[list[PushState]]
) -> None:
    assert reports(*calculations) == states


def test_record_is_dropped_when_a_report_does_not_read_it() -> None:
    reports((False,), ())

    assert store.records == {}


def test_a_load_assumes_no_pr_until_it_gives_a_result() -> None:
    reports((False,), (True,))

    assert assumes_no_pr("key", "checks", pending=True)
    assert not assumes_no_pr("key", "checks", pending=False)
    assert not assumes_no_pr("key", "checks", pending=True)
    assert assumes_no_pr("key", "reviews", pending=True)


def test_a_branch_that_was_already_pushed_assumes_nothing() -> None:
    reports((True,))

    assert not assumes_no_pr("key", "checks", pending=True)
