import pytest

from git_graph_branch.nix.cohort import Cohort, get_active_cohort, live_cohort_context
from git_graph_branch.nix.loop import once


def test_raises_outside_a_nix_context_manager() -> None:
    with pytest.raises(RuntimeError):
        get_active_cohort()


def test_returns_the_live_cohort() -> None:
    cohort = Cohort()
    with live_cohort_context(cohort):
        assert get_active_cohort() is cohort


async def test_returns_none_when_running_once() -> None:
    async with once():
        assert get_active_cohort() is None
