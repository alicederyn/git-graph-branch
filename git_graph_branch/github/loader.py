"""The GraphQL loader (ADRs 3–5).

Queries that start in the same event-loop tick are merged into one request. Each
result is a Fact. In watch mode, a background task polls each result again, at the
interval its poll policy gives, and nixes the result when it changes.

The background task cannot read the filesystem (nix forbids it), so everything that
comes from git config or the environment is in the Endpoint.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from collections.abc import Callable, Hashable, Mapping, Sequence
from contextlib import suppress
from contextvars import Context
from dataclasses import dataclass, field
from math import inf
from typing import Any

import aiohttp
import truststore

from ..nix.fact import Fact, run_background_task, when_safe_to_nix
from ..tmux import wait_until_visible
from .merge import Query, merge

TIMEOUT = 15.0
MIN_BATCH_INTERVAL = 5.0
RATE_LIMITED_INTERVAL = 300.0
LOW_RATE_LIMIT = 100

type Result = dict[str, Any] | Exception
type PollPolicy = Callable[[Result, float], float]
"""Seconds until the next poll, from the latest result and the seconds since the
query was first loaded."""


@dataclass(frozen=True)
class Endpoint:
    url: str
    token: str = field(repr=False)
    proxy: str | None
    cafile: str | None


@dataclass(frozen=True)
class Key:
    endpoint: Endpoint
    document: str
    variables: str
    version: Hashable


@dataclass(eq=False)
class Entry:
    key: Key
    query: Query
    fact: Fact
    result: asyncio.Future[Result]
    first_loaded_at: float
    poll_policy: PollPolicy
    latest: Result | None = None
    next_poll_at: float = inf


@dataclass(eq=False)
class EndpointState:
    endpoint: Endpoint
    entries: set[Entry] = field(default_factory=set)
    queue: list[Entry] = field(default_factory=list)
    dispatch_scheduled: bool = False
    last_sent_at: float = -inf
    rate_limited_until: float = -inf
    changed: asyncio.Event = field(default_factory=asyncio.Event)


entries: dict[Key, Entry] = {}
endpoints: dict[Endpoint, EndpointState] = {}
dispatch_tasks: set[asyncio.Task[None]] = set()


async def query(
    endpoint: Endpoint,
    document: str,
    variables: Mapping[str, Any],
    poll_policy: PollPolicy,
    *,
    version: Hashable = None,
) -> Result:
    """Load the result of a GraphQL query, as data or as an exception.

    Must be called in a nix report calculation. A different version gives a
    different result, even if the query is the same.
    """
    key = Key(endpoint, document, json.dumps(variables, sort_keys=True), version)
    entry = entries.get(key)
    if entry is None or entry.fact.nixed:
        entry = add_entry(key, Query(document, variables), poll_policy, entry)
    entry.poll_policy = poll_policy
    entry.fact.record_use()
    return await asyncio.shield(entry.result)


def add_entry(
    key: Key, query: Query, poll_policy: PollPolicy, previous: Entry | None
) -> Entry:
    loop = asyncio.get_running_loop()
    state = endpoint_state(key.endpoint)
    entry = Entry(key, query, Fact(), loop.create_future(), loop.time(), poll_policy)
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
        # An empty context, so the request is not part of any nix calculation
        asyncio.get_running_loop().call_soon(start_dispatch, state, context=Context())


def start_dispatch(state: EndpointState) -> None:
    task = asyncio.create_task(dispatch(state))
    dispatch_tasks.add(task)
    task.add_done_callback(dispatch_tasks.discard)


async def dispatch(state: EndpointState) -> None:
    loop = asyncio.get_running_loop()
    await asyncio.sleep(max(0.0, state.last_sent_at + MIN_BATCH_INTERVAL - loop.time()))
    batch = [entry for entry in state.queue if entry in state.entries]
    state.queue = []
    state.dispatch_scheduled = False
    if not batch:
        return
    state.last_sent_at = loop.time()
    results = await fetch(state, [entry.query for entry in batch])
    for entry, result in zip(batch, results):
        deliver(state, entry, result)


async def fetch(state: EndpointState, queries: Sequence[Query]) -> list[Result]:
    try:
        merged = merge(queries)
        body = {"query": merged.document, "variables": merged.variables}
        response, headers = await post(state.endpoint, body)
        note_rate_limit(state, headers)
        return merged.split(response)
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


def same(a: Result | None, b: Result | None) -> bool:
    if isinstance(a, Exception) and isinstance(b, Exception):
        return type(a) is type(b) and str(a) == str(b)
    return a == b


def deliver(state: EndpointState, entry: Entry, result: Result) -> None:
    if not entry.result.done():
        entry.latest = result
        entry.result.set_result(result)
    elif not same(result, entry.latest):
        when_safe_to_nix(replace_result, entry, result)
        return
    schedule_poll(state, entry)


def replace_result(entry: Entry, result: Result) -> None:
    """Keep result for the next query, and nix the old result."""
    entry.latest = result
    entry.fact.nix()


def schedule_poll(state: EndpointState, entry: Entry) -> None:
    assert entry.latest is not None
    now = asyncio.get_running_loop().time()
    delay = entry.poll_policy(entry.latest, now - entry.first_loaded_at)
    if now < state.rate_limited_until:
        delay = max(delay, RATE_LIMITED_INTERVAL)
    entry.next_poll_at = now + delay
    state.changed.set()


async def poll(state: EndpointState) -> None:
    """Send each query again when its poll is due, while the window is visible."""
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
