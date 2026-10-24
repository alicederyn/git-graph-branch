import asyncio
import ssl
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from git_graph_branch import tmux
from git_graph_branch.github import loader
from git_graph_branch.github.loader import Endpoint, query, ssl_context
from git_graph_branch.nix.fact import report_calculation, session

ENDPOINT = Endpoint("https://example.com/graphql", "token", None, None)
ECHO = "query ($n: Int!) { echo(n: $n) }"


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


async def test_queries_in_one_tick_share_one_request(
    one_shot: None, post: AsyncMock
) -> None:
    with report_calculation():
        results = await asyncio.gather(
            query(ENDPOINT, ECHO, {"n": 1}, never_poll),
            query(ENDPOINT, ECHO, {"n": 2}, never_poll),
        )

    assert list(results) == [{"echo": 1}, {"echo": 2}]
    assert post.call_count == 1


async def test_query_reuses_the_result_of_an_earlier_calculation(
    one_shot: None, post: AsyncMock
) -> None:
    with report_calculation():
        await query(ENDPOINT, ECHO, {"n": 1}, never_poll)
    with report_calculation():
        result = await query(ENDPOINT, ECHO, {"n": 1}, never_poll)

    assert result == {"echo": 1}
    assert post.call_count == 1


async def test_a_new_version_loads_again(one_shot: None, post: AsyncMock) -> None:
    with report_calculation():
        await query(ENDPOINT, ECHO, {"n": 1}, never_poll, version="a")
        await query(ENDPOINT, ECHO, {"n": 1}, never_poll, version="b")

    assert post.call_count == 2


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
        cancelled = asyncio.create_task(query(ENDPOINT, ECHO, {"n": 1}, never_poll))
        other = asyncio.create_task(query(ENDPOINT, ECHO, {"n": 1}, never_poll))
        await asyncio.sleep(0.01)
        cancelled.cancel()
        release.set()

        assert await other == {"echo": 1}


async def test_failed_request_gives_the_error_as_the_result(
    one_shot: None, post: AsyncMock
) -> None:
    post.side_effect = TimeoutError()

    with report_calculation():
        result = await query(ENDPOINT, ECHO, {"n": 1}, never_poll)

    assert isinstance(result, TimeoutError)


async def test_results_are_dropped_when_moot(post: AsyncMock) -> None:
    with session(None):
        with report_calculation():
            await query(ENDPOINT, ECHO, {"n": 1}, never_poll)

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
        await query(ENDPOINT, ECHO, {"n": 0}, poll_at_once)
    nixed = asyncio.Event()
    report.on_nix(nixed.set)

    await asyncio.wait_for(nixed.wait(), timeout=5)
    assert post.call_count == 3
    with report_calculation():
        result = await query(ENDPOINT, ECHO, {"n": 0}, never_poll)
    assert result == {"echo": 2}
    assert post.call_count == 3


async def test_poll_waits_until_the_window_is_visible(
    watching: None, post: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    visible = asyncio.Event()
    monkeypatch.setattr(tmux, "_visible", visible)
    with report_calculation():
        await query(ENDPOINT, ECHO, {"n": 0}, poll_at_once)

    await asyncio.sleep(0.05)
    assert post.call_count == 1
    visible.set()
    await asyncio.sleep(0.05)
    assert post.call_count > 1


def test_ssl_context_is_not_strict() -> None:
    """Python 3.13's strict flag rejects some corporate CA bundles."""
    assert not ssl_context(None).verify_flags & ssl.VERIFY_X509_STRICT
