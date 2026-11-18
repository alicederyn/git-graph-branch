"""The transport that sends the loader's requests to GitHub (ADRs 4, 5 and 8)."""

import asyncio
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import inf
from typing import Any

import aiohttp
import truststore

TIMEOUT = 15.0
MIN_BATCH_INTERVAL = 5.0
RATE_LIMITED_INTERVAL = 300.0
LOW_RATE_LIMIT = 100
SECONDARY_RATE_LIMIT_STATUSES = {403, 429}


@dataclass(frozen=True)
class Endpoint:
    url: str
    token: str = field(repr=False)
    proxy: str | None
    cafile: str | None

    def connect(self) -> "GitHubConnection":
        return GitHubConnection(self)


@dataclass(eq=False)
class GitHubConnection:
    endpoint: Endpoint
    rate_limited_until: float = -inf
    """Polls are slow before this time, as the hourly limit is nearly used up."""
    blocked_until: float = -inf
    """No requests start before this time, after a secondary rate limit."""

    async def post(self, body: Mapping[str, Any]) -> dict[str, Any]:
        try:
            response, headers = await post(self.endpoint, body)
        except aiohttp.ClientResponseError as e:
            if e.status in SECONDARY_RATE_LIMIT_STATUSES:
                self.note_secondary_rate_limit(e.headers or {})
            raise
        self.note_rate_limit(headers)
        return response

    def earliest_batch(self, last_batch_at: float) -> float:
        """Keep requests apart, as BBGitHub's automation policy asks (ADR 5)."""
        return max(last_batch_at + MIN_BATCH_INTERVAL, self.blocked_until)

    def poll_delay(self, delay: float) -> float:
        now = asyncio.get_running_loop().time()
        if now < self.rate_limited_until:
            delay = max(delay, RATE_LIMITED_INTERVAL)
        return max(delay, self.blocked_until - now)

    def note_rate_limit(self, headers: Mapping[str, str]) -> None:
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        if remaining is None or reset is None or int(remaining) >= LOW_RATE_LIMIT:
            return
        seconds_to_reset = max(0.0, int(reset) - time.time())
        self.rate_limited_until = asyncio.get_running_loop().time() + seconds_to_reset

    def note_secondary_rate_limit(self, headers: Mapping[str, str]) -> None:
        """Start no requests until GitHub allows them.

        GitHub can ban a client that keeps sending requests while it is limited. It
        sends retry-after, or x-ratelimit-reset if the hourly limit is used up.
        """
        if retry_after := headers.get("retry-after"):
            seconds = float(retry_after)
        elif headers.get("x-ratelimit-remaining") == "0" and (
            reset := headers.get("x-ratelimit-reset")
        ):
            seconds = max(0.0, int(reset) - time.time())
        else:
            seconds = RATE_LIMITED_INTERVAL
        blocked_until = asyncio.get_running_loop().time() + seconds
        self.blocked_until = max(self.blocked_until, blocked_until)


def ssl_context(cafile: str | None) -> ssl.SSLContext:
    """Trust the operating system's certificates, and cafile if given.

    Not ssl.create_default_context, as its VERIFY_X509_STRICT flag rejects some
    corporate CA bundles.
    """
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if cafile:
        context.load_verify_locations(cafile=cafile)
    return context


async def post(
    endpoint: Endpoint, body: Mapping[str, Any]
) -> tuple[dict[str, Any], Mapping[str, str]]:
    connector = aiohttp.TCPConnector(ssl=ssl_context(endpoint.cafile))
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async with session.post(
            endpoint.url,
            json=body,
            headers={"Authorization": f"Bearer {endpoint.token}"},
            proxy=endpoint.proxy,
        ) as response:
            response.raise_for_status()
            return await response.json(), response.headers
