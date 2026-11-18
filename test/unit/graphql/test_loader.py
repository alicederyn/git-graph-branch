import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest

from git_graph_branch import tmux
from git_graph_branch.graphql import loader
from git_graph_branch.graphql.loader import Fetch, Pending, Result, load
from git_graph_branch.nix.fact import report_calculation, session

ECHO = "query ($n: Int!) { echo(n: $n) }"


@dataclass(eq=False)
class FakeConnection:
    batch_interval: ClassVar[float] = 0.0

    async def post(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def earliest_batch(self, last_batch_at: float) -> float:
        return last_batch_at + self.batch_interval

    def poll_delay(self, delay: float) -> float:
        return delay


@dataclass(frozen=True)
class FakeTransport:
    def connect(self) -> FakeConnection:
        return FakeConnection()


TRANSPORT = FakeTransport()


async def echo(fetch: Fetch, previous: object, input: object, n: int) -> dict[str, Any]:
    return await fetch(ECHO, {"n": n})


async def echo_input(fetch: Fetch, previous: object, input: object) -> object:
    return input


def never_poll(result: object, age: float) -> float:
    return 1e9


def poll_at_once(result: object, age: float) -> float:
    return 0.0


def echo_response(body: Mapping[str, Any]) -> dict[str, Any]:
    """Answer each merged echo query with its variable."""
    variables = body["variables"]
    return {"data": {name.replace("_n", "_echo"): v for name, v in variables.items()}}


@pytest.fixture(autouse=True)
def post(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    async def respond(body: Mapping[str, Any]) -> dict[str, Any]:
        return echo_response(body)

    mock = AsyncMock(side_effect=respond)

    async def post(self: FakeConnection, body: Mapping[str, Any]) -> Any:
        return await mock(body)

    monkeypatch.setattr(FakeConnection, "post", post)
    return mock


@pytest.fixture
def one_shot() -> Iterator[None]:
    with session(None):
        yield


@pytest.fixture
async def watching() -> AsyncIterator[None]:
    async with asyncio.TaskGroup() as task_group:
        with session(task_group):
            yield


async def test_loads_in_one_tick_share_one_request(
    one_shot: None, post: AsyncMock
) -> None:
    with report_calculation():
        results = await asyncio.gather(
            load(TRANSPORT, echo, (1,), never_poll, input=None),
            load(TRANSPORT, echo, (2,), never_poll, input=None),
        )

    assert list(results) == [Result({"echo": 1}), Result({"echo": 2})]
    assert post.call_count == 1


async def test_load_reuses_the_result_of_an_earlier_calculation(
    one_shot: None, post: AsyncMock
) -> None:
    with report_calculation():
        await load(TRANSPORT, echo, (1,), never_poll, input=None)
    with report_calculation():
        result = await load(TRANSPORT, echo, (1,), never_poll, input=None)

    assert result == Result({"echo": 1})
    assert post.call_count == 1


async def test_result_contains_the_input_of_its_state(one_shot: None) -> None:
    with report_calculation():
        result = await load(TRANSPORT, echo_input, (), never_poll, input="a")

    assert result == Result("a", None, "a")


async def test_a_new_input_keeps_the_state_and_loads_again(
    watching: None, post: AsyncMock
) -> None:
    with report_calculation():
        await load(TRANSPORT, echo, (1,), never_poll, input="a")
    with report_calculation():
        result = await load(TRANSPORT, echo, (1,), never_poll, input="b", wait=False)
    await asyncio.sleep(0.05)

    assert result == Result({"echo": 1}, None, "a")
    assert post.call_count == 2


async def test_a_new_input_restarts_the_poll_age(watching: None) -> None:
    ages: list[float] = []

    def record_age(result: object, age: float) -> float:
        ages.append(age)
        return 1e9

    with report_calculation():
        await load(TRANSPORT, echo, (1,), record_age, input="a")
    await asyncio.sleep(0.1)
    with report_calculation():
        await load(TRANSPORT, echo, (1,), record_age, input="b")
    await asyncio.sleep(0.05)
    with report_calculation():
        await load(TRANSPORT, echo, (1,), record_age, input="b")

    assert len(ages) == 2
    assert ages[1] < 0.1


async def test_a_load_that_ends_with_an_old_input_loads_again(watching: None) -> None:
    started, release = asyncio.Event(), asyncio.Event()
    inputs: list[object] = []

    async def slow(fetch: Fetch, previous: object, input: object) -> object:
        inputs.append(input)
        if len(inputs) == 1:
            started.set()
            await release.wait()
        return input

    with report_calculation():
        await load(TRANSPORT, slow, (), never_poll, input="a", wait=False)
    await started.wait()
    with report_calculation() as report:
        await load(TRANSPORT, slow, (), never_poll, input="b", wait=False)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)
    release.set()
    await asyncio.wait_for(nixed.wait(), timeout=5)
    with report_calculation():
        await load(TRANSPORT, slow, (), never_poll, input="b", wait=False)
    async with asyncio.timeout(5):
        while len(inputs) < 2:
            await asyncio.sleep(0.01)

    assert inputs == ["a", "b"]


async def test_a_load_with_no_request_does_not_wait_for_the_connection(
    watching: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(FakeConnection, "batch_interval", 60.0)
    with report_calculation():
        await load(TRANSPORT, echo, (1,), never_poll, input=None)
    with report_calculation():
        result = await asyncio.wait_for(
            load(TRANSPORT, echo_input, (), never_poll, input="a"), timeout=5
        )

    assert result == Result("a", None, "a")


async def test_later_fetches_share_requests_without_waiting(
    one_shot: None, monkeypatch: pytest.MonkeyPatch, post: AsyncMock
) -> None:
    async def two_pages(
        fetch: Fetch, previous: object, input: object, n: int
    ) -> list[int]:
        first = await fetch(ECHO, {"n": n})
        second = await fetch(ECHO, {"n": n + 10})
        return [first["echo"], second["echo"]]

    monkeypatch.setattr(FakeConnection, "batch_interval", 60.0)
    with report_calculation():
        results = await asyncio.wait_for(
            asyncio.gather(
                load(TRANSPORT, two_pages, (1,), never_poll, input=None),
                load(TRANSPORT, two_pages, (2,), never_poll, input=None),
            ),
            timeout=5,
        )

    assert list(results) == [Result([1, 11]), Result([2, 12])]
    assert post.call_count == 2


async def test_load_gets_the_last_state_that_did_not_fail(watching: None) -> None:
    previous_states: list[object] = []

    async def count(fetch: Fetch, previous: object, input: object) -> int:
        previous_states.append(previous)
        if len(previous_states) == 2:
            raise TimeoutError()
        return len(previous_states)

    with report_calculation() as report:
        await load(TRANSPORT, count, (), poll_at_once, input=None)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)
    await asyncio.wait_for(nixed.wait(), timeout=5)
    with report_calculation():
        after_failure = await load(TRANSPORT, count, (), poll_at_once, input=None)
    async with asyncio.timeout(5):
        while len(previous_states) < 3:
            await asyncio.sleep(0.01)

    assert after_failure.state == 1
    assert isinstance(after_failure.error, TimeoutError)
    assert previous_states[:3] == [None, 1, 1]


async def test_cancelled_caller_does_not_cancel_other_callers(
    one_shot: None, post: AsyncMock
) -> None:
    release = asyncio.Event()

    async def respond_later(body: Mapping[str, Any]) -> dict[str, Any]:
        await release.wait()
        return echo_response(body)

    post.side_effect = respond_later
    with report_calculation():
        cancelled = asyncio.create_task(
            load(TRANSPORT, echo, (1,), never_poll, input=None)
        )
        other = asyncio.create_task(load(TRANSPORT, echo, (1,), never_poll, input=None))
        await asyncio.sleep(0.01)
        cancelled.cancel()
        release.set()

        assert await other == Result({"echo": 1})


async def test_failed_request_gives_the_error_in_the_result(
    one_shot: None, post: AsyncMock
) -> None:
    post.side_effect = TimeoutError()

    with report_calculation():
        result = await load(TRANSPORT, echo, (1,), never_poll, input=None)

    assert result.state is None
    assert isinstance(result.error, TimeoutError)


async def test_results_are_dropped_when_moot() -> None:
    with session(None):
        with report_calculation():
            await load(TRANSPORT, echo, (1,), never_poll, input=None)

    assert loader.entries == {}
    assert loader.transports == {}


async def test_poll_nixes_the_result_only_when_it_changes(
    watching: None, post: AsyncMock
) -> None:
    responses = iter([1, 1, 2])

    async def respond(body: Mapping[str, Any]) -> dict[str, Any]:
        return {"data": {"q0_echo": next(responses)}}

    post.side_effect = respond
    with report_calculation() as report:
        await load(TRANSPORT, echo, (0,), poll_at_once, input=None)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)

    await asyncio.wait_for(nixed.wait(), timeout=5)
    assert post.call_count == 3
    with report_calculation():
        result = await load(TRANSPORT, echo, (0,), never_poll, input=None)
    assert result == Result({"echo": 2})
    assert post.call_count == 3


async def test_load_without_wait_gives_pending_and_still_sends(
    watching: None, post: AsyncMock
) -> None:
    with report_calculation():
        result = await load(TRANSPORT, echo, (0,), never_poll, input=None, wait=False)
    await asyncio.sleep(0.05)

    assert result is Pending.PENDING
    assert post.call_count == 1


async def test_first_result_nixes_a_pending_load(
    watching: None, post: AsyncMock
) -> None:
    with report_calculation() as report:
        await load(TRANSPORT, echo, (0,), never_poll, input=None, wait=False)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)

    await asyncio.wait_for(nixed.wait(), timeout=5)
    with report_calculation():
        result = await load(TRANSPORT, echo, (0,), never_poll, input=None, wait=False)
    assert result == Result({"echo": 0})
    assert post.call_count == 1


async def test_load_without_wait_gives_a_loaded_result(watching: None) -> None:
    with report_calculation():
        await load(TRANSPORT, echo, (0,), never_poll, input=None)
        result = await load(TRANSPORT, echo, (0,), never_poll, input=None, wait=False)

    assert result == Result({"echo": 0})


async def test_poll_waits_until_the_window_is_visible(
    watching: None, monkeypatch: pytest.MonkeyPatch, post: AsyncMock
) -> None:
    visible = asyncio.Event()
    monkeypatch.setattr(tmux, "_visible", visible)
    with report_calculation():
        await load(TRANSPORT, echo, (0,), poll_at_once, input=None)

    await asyncio.sleep(0.05)
    assert post.call_count == 1
    visible.set()
    await asyncio.sleep(0.05)
    assert post.call_count > 1


async def test_connection_can_make_a_poll_later(
    watching: None, monkeypatch: pytest.MonkeyPatch, post: AsyncMock
) -> None:
    monkeypatch.setattr(FakeConnection, "poll_delay", lambda self, delay: 1e9)
    with report_calculation():
        await load(TRANSPORT, echo, (0,), poll_at_once, input=None)
    await asyncio.sleep(0.05)

    assert post.call_count == 1


async def test_first_request_of_a_load_waits_for_the_connection(
    watching: None, post: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(FakeConnection, "batch_interval", 0.3)
    with report_calculation():
        await load(TRANSPORT, echo, (1,), never_poll, input=None)
    with report_calculation():
        await load(TRANSPORT, echo, (2,), never_poll, input=None, wait=False)

    await asyncio.sleep(0.1)
    assert post.call_count == 1
    await asyncio.sleep(0.4)
    assert post.call_count == 2


async def test_a_request_for_an_old_input_is_not_sent(
    watching: None, post: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def echo_input_number(fetch: Fetch, previous: object, input: int) -> object:
        return await fetch(ECHO, {"n": input})

    monkeypatch.setattr(FakeConnection, "batch_interval", 0.3)
    with report_calculation():
        await load(TRANSPORT, echo, (0,), never_poll, input=None)
    with report_calculation():
        await load(TRANSPORT, echo_input_number, (), never_poll, input=1, wait=False)
    await asyncio.sleep(0.1)
    with report_calculation():
        await load(TRANSPORT, echo_input_number, (), never_poll, input=2, wait=False)
    await asyncio.sleep(0.5)

    assert post.call_count == 2
    assert list(post.call_args.args[0]["variables"].values()) == [2]


async def test_a_failed_load_for_a_new_input_does_not_load_again(
    watching: None,
) -> None:
    inputs: list[object] = []

    async def fail_after_first(fetch: Fetch, previous: object, input: object) -> object:
        inputs.append(input)
        if len(inputs) > 1:
            raise TimeoutError()
        return input

    with report_calculation():
        await load(TRANSPORT, fail_after_first, (), never_poll, input="a")
    with report_calculation():
        await load(TRANSPORT, fail_after_first, (), never_poll, input="b")
    await asyncio.sleep(0.05)
    with report_calculation():
        result = await load(TRANSPORT, fail_after_first, (), never_poll, input="b")
    await asyncio.sleep(0.05)

    assert inputs == ["a", "b"]
    assert result.input == "a"
    assert isinstance(result.error, TimeoutError)
