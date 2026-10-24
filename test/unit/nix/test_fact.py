import asyncio
from collections.abc import Iterator
from unittest.mock import Mock

import pytest

from git_graph_branch.nix.fact import (
    Fact,
    NixError,
    release_moot_facts,
    report_calculation,
    run_background_task,
    session,
    when_safe_to_nix,
)


@pytest.fixture
def one_shot() -> Iterator[None]:
    with session(None):
        yield


def calculate_report(*facts: Fact) -> Fact:
    with report_calculation() as report:
        for fact in facts:
            fact.record_use()
    return report


def test_nix_cascades_to_dependent_calculations(one_shot: None) -> None:
    source = Fact()
    derived = Fact()
    with report_calculation() as report:
        with derived.calculation():
            source.record_use()

    source.nix()

    assert derived.nixed
    assert report.nixed


def test_nix_does_not_cascade_to_independent_calculations(one_shot: None) -> None:
    source = Fact()
    report = calculate_report(Fact())

    source.nix()

    assert not report.nixed


def test_record_use_outside_a_report_calculation_raises(one_shot: None) -> None:
    with pytest.raises(NixError):
        Fact().record_use()


def test_record_use_in_a_calculation_outside_a_report_raises(one_shot: None) -> None:
    with Fact().calculation(), pytest.raises(NixError):
        Fact().record_use()


def test_record_use_of_a_nixed_fact_raises(one_shot: None) -> None:
    fact = Fact()
    fact.nix()
    with report_calculation(), pytest.raises(NixError):
        fact.record_use()


async def test_record_use_after_the_calculation_finished_raises(
    one_shot: None,
) -> None:
    fact = Fact()

    async def use_later() -> None:
        await asyncio.sleep(0)
        fact.record_use()

    with report_calculation():
        task = asyncio.create_task(use_later())

    with pytest.raises(NixError):
        await task


def test_nix_during_a_report_calculation_raises(one_shot: None) -> None:
    fact = Fact()
    with report_calculation(), pytest.raises(NixError):
        fact.nix()


def test_calculation_without_nixable_dependencies_is_constant(
    one_shot: None,
) -> None:
    constant = Fact()
    with constant.calculation():
        pass
    calculate_report(constant)

    release_moot_facts()

    assert not constant.moot
    constant.record_use()  # Does not raise outside a report calculation


def test_callback_runs_once_for_chained_events(one_shot: None) -> None:
    fact = Fact()
    callback = Mock()
    fact.on_nix(fact.on_moot(callback, "key"))

    fact.nix()
    calculate_report()
    release_moot_facts()

    assert fact.moot
    callback.assert_called_once_with("key")


def test_callback_registered_after_event_runs_immediately(one_shot: None) -> None:
    fact = Fact()
    fact.nix()
    callback = Mock()

    fact.on_nix(callback)

    callback.assert_called_once_with()


def test_facts_the_current_report_does_not_use_go_moot(one_shot: None) -> None:
    used = Fact()
    unused = Fact()
    calculate_report(used, unused)
    calculate_report(used)

    release_moot_facts()

    assert not used.moot
    assert unused.moot


def test_facts_of_a_nixed_current_report_do_not_go_moot(one_shot: None) -> None:
    used = Fact()
    source = Fact()
    calculate_report(used, source)
    source.nix()

    release_moot_facts()

    assert not used.moot


def test_all_facts_go_moot_when_the_session_ends() -> None:
    with session(None):
        fact = Fact()
        calculate_report(fact)

    assert fact.moot


def test_when_safe_to_nix_waits_for_the_report_calculation(one_shot: None) -> None:
    fact = Fact()
    with report_calculation():
        fact.record_use()
        when_safe_to_nix(fact.nix)
        assert not fact.nixed

    assert fact.nixed


def test_when_safe_to_nix_callback_cannot_start_a_calculation(
    one_shot: None,
) -> None:
    def calculate() -> None:
        with Fact().calculation():
            pass

    with pytest.raises(NixError):
        when_safe_to_nix(calculate)


async def test_background_task_cannot_create_facts() -> None:
    errors: list[NixError] = []

    async def background() -> None:
        try:
            Fact()
        except NixError as e:
            errors.append(e)

    async with asyncio.TaskGroup() as task_group:
        with session(task_group):
            run_background_task(background())
            await asyncio.sleep(0)

    assert errors
