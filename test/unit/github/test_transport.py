import asyncio
import ssl
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from multidict import CIMultiDict

from git_graph_branch.github import transport
from git_graph_branch.github.transport import (
    MIN_BATCH_INTERVAL,
    RATE_LIMITED_INTERVAL,
    Endpoint,
    ssl_context,
)

ENDPOINT = Endpoint("https://example.com/graphql", "token", None, None)


@pytest.fixture(autouse=True)
def post() -> Iterator[AsyncMock]:
    with patch.object(transport, "post", new=AsyncMock(return_value=({}, {}))) as mock:
        yield mock


def http_error(status: int, headers: dict[str, str]) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        Mock(), (), status=status, headers=CIMultiDict(headers)
    )


def now() -> float:
    return asyncio.get_running_loop().time()


async def test_requests_are_kept_apart() -> None:
    connection = ENDPOINT.connect()

    assert connection.earliest_batch(100.0) == 100.0 + MIN_BATCH_INTERVAL


@pytest.mark.parametrize(
    "headers",
    [
        {"retry-after": "60"},
        {
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(int(time.time()) + 600),
        },
        {},
    ],
    ids=["retry-after", "hourly limit used up", "no headers"],
)
@pytest.mark.parametrize("status", [403, 429])
async def test_secondary_rate_limit_stops_requests(
    post: AsyncMock, status: int, headers: dict[str, str]
) -> None:
    post.side_effect = http_error(status, headers)
    connection = ENDPOINT.connect()

    with pytest.raises(aiohttp.ClientResponseError):
        await connection.post({})

    assert connection.earliest_batch(-1e9) > now() + 10
    assert connection.poll_delay(0.0) > 10


async def test_server_error_does_not_stop_requests(post: AsyncMock) -> None:
    post.side_effect = http_error(500, {})
    connection = ENDPOINT.connect()

    with pytest.raises(aiohttp.ClientResponseError):
        await connection.post({})

    assert connection.earliest_batch(-1e9) < now()
    assert connection.poll_delay(0.0) == 0.0


async def test_low_rate_limit_slows_polls(post: AsyncMock) -> None:
    headers = {
        "x-ratelimit-remaining": "10",
        "x-ratelimit-reset": str(int(time.time()) + 600),
    }
    post.return_value = ({"data": {}}, headers)
    connection = ENDPOINT.connect()

    assert await connection.post({}) == {"data": {}}
    assert connection.poll_delay(0.0) == RATE_LIMITED_INTERVAL
    assert connection.earliest_batch(-1e9) < now()


def test_ssl_context_is_not_strict() -> None:
    """Python 3.13's strict flag rejects some corporate CA bundles."""
    assert not ssl_context(None).verify_flags & ssl.VERIFY_X509_STRICT
