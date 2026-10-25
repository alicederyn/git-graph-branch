import asyncio
import ssl
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from multidict import CIMultiDict

from git_graph_branch import tmux
from git_graph_branch.github import loader
from git_graph_branch.github.loader import (
    Endpoint,
    Fetch,
    Pending,
    Result,
    load,
    ssl_context,
)
from git_graph_branch.nix.fact import report_calculation, session

ENDPOINT = Endpoint("https://example.com/graphql", "token", None, None)
ECHO = "query ($n: Int!) { echo(n: $n) }"


async def echo(fetch: Fetch, previous: object, n: int) -> dict[str, Any]:
    return await fetch(ECHO, {"n": n})


def never_poll(result: object, age: float) -> float:
    return 1e9


def poll_at_once(result: object, age: float) -> float:
    return 0.0


def echo_response(body: Mapping[str, Any]) -> dict[str, Any]:
    """Answer each merged echo query with its variable."""
    variables = body["variables"]
    return {"data": {name.replace("_n", "_echo"): v for name, v in variables.items()}}


@pytest.fixture(autouse=True)
def post() -> Iterator[AsyncMock]:
    async def respond(
        endpoint: Endpoint, body: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return echo_response(body), {}

    with patch.object(loader, "post", new=AsyncMock(side_effect=respond)) as mock:
        yield mock


@pytest.fixture(autouse=True)
def MIN_BATCH_INTERVAL(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "MIN_BATCH_INTERVAL", 0.0)


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
            load(ENDPOINT, echo, (1,), never_poll),
            load(ENDPOINT, echo, (2,), never_poll),
        )

    assert list(results) == [Result({"echo": 1}), Result({"echo": 2})]
    assert post.call_count == 1


async def test_load_reuses_the_result_of_an_earlier_calculation(
    one_shot: None, post: AsyncMock
) -> None:
    with report_calculation():
        await load(ENDPOINT, echo, (1,), never_poll)
    with report_calculation():
        result = await load(ENDPOINT, echo, (1,), never_poll)

    assert result == Result({"echo": 1})
    assert post.call_count == 1


async def test_a_new_version_loads_again(one_shot: None, post: AsyncMock) -> None:
    with report_calculation():
        await load(ENDPOINT, echo, (1,), never_poll, version="a")
        await load(ENDPOINT, echo, (1,), never_poll, version="b")

    assert post.call_count == 2


async def test_later_fetches_share_requests_without_waiting(
    one_shot: None, post: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def two_pages(fetch: Fetch, previous: object, n: int) -> list[int]:
        first = await fetch(ECHO, {"n": n})
        second = await fetch(ECHO, {"n": n + 10})
        return [first["echo"], second["echo"]]

    monkeypatch.setattr(loader, "MIN_BATCH_INTERVAL", 60.0)
    with report_calculation():
        results = await asyncio.wait_for(
            asyncio.gather(
                load(ENDPOINT, two_pages, (1,), never_poll),
                load(ENDPOINT, two_pages, (2,), never_poll),
            ),
            timeout=5,
        )

    assert list(results) == [Result([1, 11]), Result([2, 12])]
    assert post.call_count == 2


async def test_load_gets_the_last_state_that_did_not_fail(watching: None) -> None:
    previous_states: list[object] = []

    async def count(fetch: Fetch, previous: object) -> int:
        previous_states.append(previous)
        if len(previous_states) == 2:
            raise TimeoutError()
        return len(previous_states)

    with report_calculation() as report:
        await load(ENDPOINT, count, (), poll_at_once)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)
    await asyncio.wait_for(nixed.wait(), timeout=5)
    with report_calculation():
        after_failure = await load(ENDPOINT, count, (), poll_at_once)
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

    async def respond_later(
        endpoint: Endpoint, body: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        await release.wait()
        return echo_response(body), {}

    post.side_effect = respond_later
    with report_calculation():
        cancelled = asyncio.create_task(load(ENDPOINT, echo, (1,), never_poll))
        other = asyncio.create_task(load(ENDPOINT, echo, (1,), never_poll))
        await asyncio.sleep(0.01)
        cancelled.cancel()
        release.set()

        assert await other == Result({"echo": 1})


async def test_failed_request_gives_the_error_in_the_result(
    one_shot: None, post: AsyncMock
) -> None:
    post.side_effect = TimeoutError()

    with report_calculation():
        result = await load(ENDPOINT, echo, (1,), never_poll)

    assert result.state is None
    assert isinstance(result.error, TimeoutError)


async def test_results_are_dropped_when_moot(post: AsyncMock) -> None:
    with session(None):
        with report_calculation():
            await load(ENDPOINT, echo, (1,), never_poll)

    assert loader.entries == {}
    assert loader.endpoints == {}


async def test_poll_nixes_the_result_only_when_it_changes(
    watching: None, post: AsyncMock
) -> None:
    responses = iter([1, 1, 2])

    async def respond(
        endpoint: Endpoint, body: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return {"data": {"q0_echo": next(responses)}}, {}

    post.side_effect = respond
    with report_calculation() as report:
        await load(ENDPOINT, echo, (0,), poll_at_once)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)

    await asyncio.wait_for(nixed.wait(), timeout=5)
    assert post.call_count == 3
    with report_calculation():
        result = await load(ENDPOINT, echo, (0,), never_poll)
    assert result == Result({"echo": 2})
    assert post.call_count == 3


async def test_load_without_wait_gives_pending_and_still_sends(
    watching: None, post: AsyncMock
) -> None:
    with report_calculation():
        result = await load(ENDPOINT, echo, (0,), never_poll, wait=False)
    await asyncio.sleep(0.05)

    assert result is Pending.PENDING
    assert post.call_count == 1


async def test_first_result_nixes_a_pending_load(
    watching: None, post: AsyncMock
) -> None:
    with report_calculation() as report:
        await load(ENDPOINT, echo, (0,), never_poll, wait=False)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)

    await asyncio.wait_for(nixed.wait(), timeout=5)
    with report_calculation():
        result = await load(ENDPOINT, echo, (0,), never_poll, wait=False)
    assert result == Result({"echo": 0})
    assert post.call_count == 1


async def test_load_without_wait_gives_a_loaded_result(
    watching: None, post: AsyncMock
) -> None:
    with report_calculation():
        await load(ENDPOINT, echo, (0,), never_poll)
        result = await load(ENDPOINT, echo, (0,), never_poll, wait=False)

    assert result == Result({"echo": 0})


async def test_poll_waits_until_the_window_is_visible(
    watching: None, post: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    visible = asyncio.Event()
    monkeypatch.setattr(tmux, "_visible", visible)
    with report_calculation():
        await load(ENDPOINT, echo, (0,), poll_at_once)

    await asyncio.sleep(0.05)
    assert post.call_count == 1
    visible.set()
    await asyncio.sleep(0.05)
    assert post.call_count > 1


def http_error(status: int, headers: dict[str, str]) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        Mock(), (), status=status, headers=CIMultiDict(headers)
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"retry-after": "60"},
        {
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(int(time.time()) + 60),
        },
        {},
    ],
    ids=["retry-after", "hourly limit used up", "no headers"],
)
@pytest.mark.parametrize("status", [403, 429])
async def test_secondary_rate_limit_stops_polls(
    watching: None, post: AsyncMock, status: int, headers: dict[str, str]
) -> None:
    post.side_effect = http_error(status, headers)
    with report_calculation():
        result = await load(ENDPOINT, echo, (0,), poll_at_once)
    await asyncio.sleep(0.05)

    assert isinstance(result.error, aiohttp.ClientResponseError)
    assert post.call_count == 1


async def test_server_error_does_not_stop_polls(
    watching: None, post: AsyncMock
) -> None:
    post.side_effect = http_error(500, {})
    with report_calculation():
        await load(ENDPOINT, echo, (0,), poll_at_once)
    await asyncio.sleep(0.05)

    assert post.call_count > 1


def test_ssl_context_is_not_strict() -> None:
    """Python 3.13's strict flag rejects some corporate CA bundles."""
    assert not ssl_context(None).verify_flags & ssl.VERIFY_X509_STRICT
