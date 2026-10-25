"""The GraphQL loader (ADRs 3–5, 7).

A component loads data with a load function, which calls `fetch` once for each
GraphQL document it needs. Fetches that start in the same event-loop tick are
merged into one request. Each state that a load function returns is a Fact. In
watch mode, a background task polls each state again, at the interval its poll
policy gives, and nixes the state when it changes. A load that does not wait gets
Pending until its first state arrives, which nixes it.

The background task cannot read the filesystem (nix forbids it), so everything that
comes from git config or the environment is in the Endpoint.
"""

import asyncio
import ssl
import time
from collections.abc import Awaitable, Callable, Coroutine, Hashable, Mapping, Sequence
from contextlib import suppress
from contextvars import Context
from dataclasses import dataclass, field
from enum import Enum, auto
from math import inf
from typing import Any, Literal, overload

import aiohttp
import truststore

from ..nix.fact import Fact, run_background_task, when_safe_to_nix
from ..tmux import wait_until_visible
from .merge import Query, merge

TIMEOUT = 15.0
MIN_BATCH_INTERVAL = 5.0
RATE_LIMITED_INTERVAL = 300.0
LOW_RATE_LIMIT = 100
SECONDARY_RATE_LIMIT_STATUSES = {403, 429}

type Response = dict[str, Any] | Exception
type Fetch = Callable[[str, Mapping[str, Any]], Awaitable[dict[str, Any]]]
"""Send a GraphQL document with its variables, and return its data.

Raises QueryError if GitHub returns errors for the document."""
type LoadFunction[S, *Ts] = Callable[[Fetch, S | None, *Ts], Awaitable[S]]
"""Load a new state, from the state of the last load that did not fail."""


class Pending(Enum):
    PENDING = auto()


@dataclass(frozen=True)
class Result[S]:
    state: S | None
    """The state of the last load that did not fail, or None if none has."""
    error: Exception | None = None
    """The error of the latest load, if it failed."""


type PollPolicy[S] = Callable[[Result[S], float], float]
"""Seconds until the next poll, from the latest result and the seconds since the
state was first loaded."""


@dataclass(frozen=True)
class Endpoint:
    url: str
    token: str = field(repr=False)
    proxy: str | None
    cafile: str | None


@dataclass(frozen=True)
class Key:
    endpoint: Endpoint
    load_function: Callable[..., Awaitable[Any]]
    args: tuple[Hashable, ...]


@dataclass(eq=False)
class Entry:
    key: Key
    fact: Fact
    result: asyncio.Future[Any]
    first_loaded_at: float
    poll_policy: PollPolicy[Any]
    version: Hashable
    latest: Result[Any] | None = None
    next_poll_at: float = inf
    served_pending: bool = False


@dataclass(eq=False)
class EndpointState:
    endpoint: Endpoint
    entries: set[Entry] = field(default_factory=set)
    queue: list[Entry] = field(default_factory=list)
    dispatch_scheduled: bool = False
    last_started_at: float = -inf
    fetches: list[tuple[Query, asyncio.Future[Response]]] = field(default_factory=list)
    rate_limited_until: float = -inf
    blocked_until: float = -inf
    """No loads start before this time, after a secondary rate limit."""
    changed: asyncio.Event = field(default_factory=asyncio.Event)


entries: dict[Key, Entry] = {}
endpoints: dict[Endpoint, EndpointState] = {}
tasks: set[asyncio.Task[None]] = set()


@overload
async def load[S, *Ts](
    endpoint: Endpoint,
    load_function: LoadFunction[S, *Ts],
    args: tuple[*Ts],
    poll_policy: PollPolicy[S],
    *,
    version: Hashable = None,
    wait: Literal[True] = True,
) -> Result[S]: ...


@overload
async def load[S, *Ts](
    endpoint: Endpoint,
    load_function: LoadFunction[S, *Ts],
    args: tuple[*Ts],
    poll_policy: PollPolicy[S],
    *,
    version: Hashable = None,
    wait: bool,
) -> Result[S] | Pending: ...


async def load[S, *Ts](
    endpoint: Endpoint,
    load_function: LoadFunction[S, *Ts],
    args: tuple[*Ts],
    poll_policy: PollPolicy[S],
    *,
    version: Hashable = None,
    wait: bool = True,
) -> Result[S] | Pending:
    """Load a state with load_function(fetch, previous_state, *args).

    Must be called in a nix report calculation. The args must be hashable. If the
    load function raises an exception, the result keeps the last state, with the
    exception as its error.

    When the version changes, the state loads again at once, and the age that the
    poll policy gets starts again from zero. Until the new state arrives, the load
    gives the previous one.

    If wait is false, and the state has not loaded, return Pending; the load
    still runs, and its state nixes the calculation when it arrives.
    """
    key = Key(endpoint, load_function, args)
    entry = entries.get(key)
    if entry is None or entry.fact.nixed:
        entry = add_entry(key, poll_policy, version, entry)
    if entry.version != version:
        restart(entry, version)
    entry.poll_policy = poll_policy
    entry.fact.record_use()
    if not wait and not entry.result.done():
        entry.served_pending = True
        return Pending.PENDING
    return await asyncio.shield(entry.result)


def add_entry(
    key: Key, poll_policy: PollPolicy[Any], version: Hashable, previous: Entry | None
) -> Entry:
    loop = asyncio.get_running_loop()
    state = endpoint_state(key.endpoint)
    if previous is not None:
        version = previous.version
    entry = Entry(key, Fact(), loop.create_future(), loop.time(), poll_policy, version)
    entry.fact.on_moot(drop, entry)
    entries[key] = entry
    state.entries.add(entry)
    if previous is not None and previous.latest is not None:
        state.entries.discard(previous)
        entry.first_loaded_at = previous.first_loaded_at
        entry.latest = previous.latest
        entry.result.set_result(previous.latest)
        schedule_poll(state, entry)
    else:
        enqueue(state, entry)
    return entry


def restart(entry: Entry, version: Hashable) -> None:
    """Load again at once, and poll as if the state was first loaded now."""
    entry.version = version
    entry.first_loaded_at = asyncio.get_running_loop().time()
    if entry.next_poll_at != inf:
        entry.next_poll_at = inf
        enqueue(endpoint_state(entry.key.endpoint), entry)


def endpoint_state(endpoint: Endpoint) -> EndpointState:
    state = endpoints.get(endpoint)
    if state is None:
        state = endpoints[endpoint] = EndpointState(endpoint)
        run_background_task(poll(state))
    return state


def drop(entry: Entry) -> None:
    if entries.get(entry.key) is entry:
        del entries[entry.key]
    state = endpoints.get(entry.key.endpoint)
    if state is not None:
        state.entries.discard(entry)
        if not state.entries:
            del endpoints[entry.key.endpoint]
        state.changed.set()


def enqueue(state: EndpointState, entry: Entry) -> None:
    state.queue.append(entry)
    if not state.dispatch_scheduled:
        state.dispatch_scheduled = True
        # An empty context, so the loads are not part of any nix calculation
        asyncio.get_running_loop().call_soon(
            start_task, dispatch(state), context=Context()
        )


def start_task(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def dispatch(state: EndpointState) -> None:
    """Start the queued loads together, so that their fetches share requests."""
    loop = asyncio.get_running_loop()
    start_at = max(state.last_started_at + MIN_BATCH_INTERVAL, state.blocked_until)
    await asyncio.sleep(max(0.0, start_at - loop.time()))
    batch = [entry for entry in state.queue if entry in state.entries]
    state.queue = []
    state.dispatch_scheduled = False
    if not batch:
        return
    state.last_started_at = loop.time()
    await asyncio.gather(*(run_load(state, entry) for entry in batch))


async def run_load(state: EndpointState, entry: Entry) -> None:
    async def fetch(document: str, variables: Mapping[str, Any]) -> dict[str, Any]:
        return await fetch_in_batch(state, Query(document, variables))

    previous = entry.latest.state if entry.latest else None
    try:
        result = Result(await entry.key.load_function(fetch, previous, *entry.key.args))
    except Exception as e:
        result = Result(previous, e)
    deliver(state, entry, result)


async def fetch_in_batch(state: EndpointState, query: Query) -> dict[str, Any]:
    future: asyncio.Future[Response] = asyncio.get_running_loop().create_future()
    state.fetches.append((query, future))
    if len(state.fetches) == 1:
        asyncio.get_running_loop().call_soon(
            start_task, send_fetches(state), context=Context()
        )
    response = await future
    if isinstance(response, Exception):
        raise response
    return response


async def send_fetches(state: EndpointState) -> None:
    batch, state.fetches = state.fetches, []
    responses = await fetch(state, [query for query, _ in batch])
    for (_, future), response in zip(batch, responses):
        future.set_result(response)


async def fetch(state: EndpointState, queries: Sequence[Query]) -> list[Response]:
    try:
        merged = merge(queries)
        body = {"query": merged.document, "variables": merged.variables}
        response, headers = await post(state.endpoint, body)
        note_rate_limit(state, headers)
        return merged.split(response)
    except aiohttp.ClientResponseError as e:
        if e.status in SECONDARY_RATE_LIMIT_STATUSES:
            note_secondary_rate_limit(state, e.headers or {})
        return [e] * len(queries)
    except Exception as e:
        return [e] * len(queries)


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


def note_rate_limit(state: EndpointState, headers: Mapping[str, str]) -> None:
    remaining = headers.get("x-ratelimit-remaining")
    reset = headers.get("x-ratelimit-reset")
    if remaining is None or reset is None or int(remaining) >= LOW_RATE_LIMIT:
        return
    seconds_to_reset = max(0.0, int(reset) - time.time())
    state.rate_limited_until = asyncio.get_running_loop().time() + seconds_to_reset


def note_secondary_rate_limit(state: EndpointState, headers: Mapping[str, str]) -> None:
    """Start no loads until GitHub allows them.

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
    state.blocked_until = max(state.blocked_until, blocked_until)


def same_error(a: Exception | None, b: Exception | None) -> bool:
    if a is None or b is None:
        return a is b
    return type(a) is type(b) and str(a) == str(b)


def same(a: Result[Any], b: Result[Any] | None) -> bool:
    return b is not None and a.state == b.state and same_error(a.error, b.error)


def deliver(state: EndpointState, entry: Entry, result: Result[Any]) -> None:
    if not entry.result.done():
        entry.latest = result
        entry.result.set_result(result)
        if entry.served_pending:
            when_safe_to_nix(replace_result, entry, result)
            return
    elif not same(result, entry.latest):
        when_safe_to_nix(replace_result, entry, result)
        return
    schedule_poll(state, entry)


def replace_result(entry: Entry, result: Result[Any]) -> None:
    """Keep result for the next load, and nix the old result."""
    entry.latest = result
    entry.fact.nix()


def schedule_poll(state: EndpointState, entry: Entry) -> None:
    assert entry.latest is not None
    now = asyncio.get_running_loop().time()
    delay = entry.poll_policy(entry.latest, now - entry.first_loaded_at)
    if now < state.rate_limited_until:
        delay = max(delay, RATE_LIMITED_INTERVAL)
    delay = max(delay, state.blocked_until - now)
    entry.next_poll_at = now + delay
    state.changed.set()


async def poll(state: EndpointState) -> None:
    """Run each load again when its poll is due, while the window is visible."""
    loop = asyncio.get_running_loop()
    while endpoints.get(state.endpoint) is state:
        state.changed.clear()
        next_poll_at = min((e.next_poll_at for e in state.entries), default=inf)
        if next_poll_at > loop.time():
            timeout = None if next_poll_at == inf else next_poll_at - loop.time()
            with suppress(TimeoutError):
                await asyncio.wait_for(state.changed.wait(), timeout)
            continue
        await wait_until_visible()
        now = loop.time()
        for entry in state.entries:
            if entry.next_poll_at <= now and not entry.fact.nixed:
                entry.next_poll_at = inf
                enqueue(state, entry)
