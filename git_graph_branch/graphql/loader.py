"""The GraphQL loader (ADRs 3, 4, 6, 7 and 8).

A component loads data with a load function, which calls `fetch` once for each
GraphQL document it needs. Fetches that start in the same event-loop tick are
merged into one request. Each state that a load function returns is a Fact. In
watch mode, a background task polls each state again, at the interval its poll
policy gives, and nixes the state when it changes. A load that does not wait gets
Pending until its first state arrives, which nixes it.

The loader contains no rules about the server. A transport sends the requests,
and its connection says when they can be sent. The background task cannot read
the filesystem (nix forbids it), so everything that the transport needs from git
config or the environment is in the transport.
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Hashable, Mapping, Sequence
from contextlib import suppress
from contextvars import Context
from dataclasses import dataclass, field
from enum import Enum, auto
from math import inf
from typing import Any, Literal, Protocol, overload

from ..nix.fact import Fact, run_background_task, when_safe_to_nix
from ..tmux import wait_until_visible
from .merge import Query, merge

type Response = dict[str, Any] | Exception
type Fetch = Callable[[str, Mapping[str, Any]], Awaitable[dict[str, Any]]]
"""Send a GraphQL document with its variables, and return its data.

Raises QueryError if the server returns errors for the document."""
type LoadFunction[S, I, *Ts] = Callable[[Fetch, S | None, I, *Ts], Awaitable[S]]
"""Load a new state for an input, from the state of the last load that did not
fail."""


class Connection(Protocol):
    async def post(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Send a GraphQL request body, and return the response body."""
        ...

    def earliest_batch(self, last_batch_at: float) -> float:
        """The loop time before which the first request of a load must not be
        sent, from the loop time when the last one was sent."""
        ...

    def poll_delay(self, delay: float) -> float:
        """The seconds until the next poll, from what the poll policy gives."""
        ...


class Transport(Hashable, Protocol):
    def connect(self) -> Connection: ...


class Pending(Enum):
    PENDING = auto()


@dataclass(frozen=True)
class Result[S]:
    state: S | None
    """The state of the last load that did not fail, or None if none has."""
    error: Exception | None = None
    """The error of the latest load, if it failed."""
    input: Any = None
    """The input that the state was loaded with."""


type PollPolicy[S] = Callable[[Result[S], float], float]
"""Seconds until the next poll, from the latest result and the seconds since the
state was first loaded, or since the input changed."""


@dataclass(frozen=True)
class Key:
    transport: Transport
    load_function: Callable[..., Awaitable[Any]]
    args: tuple[Hashable, ...]


class _NoLoad(Enum):
    NO_LOAD = auto()


class _Superseded(Exception):
    """The entry was dropped, or its input changed, before the first request of
    its load was sent."""


@dataclass(eq=False)
class Entry:
    key: Key
    fact: Fact
    result: asyncio.Future[Any]
    first_loaded_at: float
    poll_policy: PollPolicy[Any]
    input: Hashable
    loaded_input: Hashable = _NoLoad.NO_LOAD
    """The input of the last load that is complete, whether it failed or not."""
    latest: Result[Any] | None = None
    next_poll_at: float = inf
    """When to poll, or inf if a load is queued or running."""
    served_pending: bool = False


@dataclass(frozen=True)
class FirstFetch:
    query: Query
    future: "asyncio.Future[Response]"
    entry: Entry
    input: Hashable


@dataclass(eq=False)
class TransportState:
    transport: Transport
    connection: Connection
    entries: set[Entry] = field(default_factory=set)
    queue: list[Entry] = field(default_factory=list)
    dispatch_scheduled: bool = False
    last_batch_at: float = -inf
    first_fetches: list[FirstFetch] = field(default_factory=list)
    """The first fetch of each load, which waits for the connection."""
    fetches: list[tuple[Query, asyncio.Future[Response]]] = field(default_factory=list)
    changed: asyncio.Event = field(default_factory=asyncio.Event)


entries: dict[Key, Entry] = {}
transports: dict[Transport, TransportState] = {}
tasks: set[asyncio.Task[None]] = set()


@overload
async def load[S, I, *Ts](
    transport: Transport,
    load_function: LoadFunction[S, I, *Ts],
    args: tuple[*Ts],
    poll_policy: PollPolicy[S],
    *,
    input: I,
    wait: Literal[True] = True,
) -> Result[S]: ...


@overload
async def load[S, I, *Ts](
    transport: Transport,
    load_function: LoadFunction[S, I, *Ts],
    args: tuple[*Ts],
    poll_policy: PollPolicy[S],
    *,
    input: I,
    wait: bool,
) -> Result[S] | Pending: ...


async def load[S, I, *Ts](
    transport: Transport,
    load_function: LoadFunction[S, I, *Ts],
    args: tuple[*Ts],
    poll_policy: PollPolicy[S],
    *,
    input: I,
    wait: bool = True,
) -> Result[S] | Pending:
    """Load a state with load_function(fetch, previous_state, input, *args).

    Must be called in a nix report calculation. The args and the input must be
    hashable. If the load function raises an exception, the result keeps the last
    state, with the exception as its error.

    When the input changes, the state loads again at once, or when the load that
    is running is complete, and the age that the poll policy gets starts again
    from zero. Until the new state arrives, the load gives the previous one.
    Each result contains the input that its state was loaded with.

    If wait is false, and the state has not loaded, return Pending; the load
    still runs, and its state nixes the calculation when it arrives.
    """
    key = Key(transport, load_function, args)
    entry = entries.get(key)
    if entry is None or entry.fact.nixed:
        entry = add_entry(key, poll_policy, input, entry)
    if entry.input != input:
        change_input(entry, input)
    entry.poll_policy = poll_policy
    entry.fact.record_use()
    if not wait and not entry.result.done():
        entry.served_pending = True
        return Pending.PENDING
    return await asyncio.shield(entry.result)


def add_entry(
    key: Key, poll_policy: PollPolicy[Any], input: Hashable, previous: Entry | None
) -> Entry:
    loop = asyncio.get_running_loop()
    state = transport_state(key.transport)
    entry = Entry(key, Fact(), loop.create_future(), loop.time(), poll_policy, input)
    entry.fact.on_moot(drop, entry)
    entries[key] = entry
    state.entries.add(entry)
    if previous is not None and previous.latest is not None:
        state.entries.discard(previous)
        entry.input = previous.input
        entry.loaded_input = previous.loaded_input
        entry.first_loaded_at = previous.first_loaded_at
        entry.latest = previous.latest
        entry.result.set_result(previous.latest)
        poll_or_reload(state, entry)
    else:
        enqueue(state, entry)
    return entry


def change_input(entry: Entry, input: Hashable) -> None:
    """Load again for the new input, and poll as if the state was first loaded
    now."""
    entry.input = input
    entry.first_loaded_at = asyncio.get_running_loop().time()
    if entry.next_poll_at != inf:
        entry.next_poll_at = inf
        enqueue(transport_state(entry.key.transport), entry)


def transport_state(transport: Transport) -> TransportState:
    state = transports.get(transport)
    if state is None:
        state = transports[transport] = TransportState(transport, transport.connect())
        run_background_task(poll(state))
    return state


def drop(entry: Entry) -> None:
    if entries.get(entry.key) is entry:
        del entries[entry.key]
    state = transports.get(entry.key.transport)
    if state is not None:
        state.entries.discard(entry)
        if not state.entries:
            del transports[entry.key.transport]
        state.changed.set()


def enqueue(state: TransportState, entry: Entry) -> None:
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


async def dispatch(state: TransportState) -> None:
    """Start the queued loads together, so that their fetches share requests."""
    batch = [entry for entry in state.queue if entry in state.entries]
    state.queue = []
    state.dispatch_scheduled = False
    await asyncio.gather(*(run_load(state, entry) for entry in batch))


async def run_load(state: TransportState, entry: Entry) -> None:
    first = True

    async def fetch(document: str, variables: Mapping[str, Any]) -> dict[str, Any]:
        nonlocal first
        is_first, first = first, False
        query = Query(document, variables)
        if is_first:
            return await first_fetch(state, query, entry, input)
        return await fetch_in_batch(state, query)

    previous = entry.latest
    input = entry.input
    try:
        loaded = await entry.key.load_function(
            fetch, previous.state if previous else None, input, *entry.key.args
        )
        result = Result(loaded, None, input)
    except _Superseded:
        if entry in state.entries:
            enqueue(state, entry)
        return
    except Exception as e:
        result = Result(
            previous.state if previous else None,
            e,
            previous.input if previous else None,
        )
    entry.loaded_input = input
    deliver(state, entry, result)


async def first_fetch(
    state: TransportState, query: Query, entry: Entry, input: Hashable
) -> dict[str, Any]:
    future: asyncio.Future[Response] = asyncio.get_running_loop().create_future()
    state.first_fetches.append(FirstFetch(query, future, entry, input))
    if len(state.first_fetches) == 1:
        asyncio.get_running_loop().call_soon(
            start_task, send_first_fetches(state), context=Context()
        )
    return response_data(await future)


async def fetch_in_batch(state: TransportState, query: Query) -> dict[str, Any]:
    future: asyncio.Future[Response] = asyncio.get_running_loop().create_future()
    state.fetches.append((query, future))
    if len(state.fetches) == 1:
        asyncio.get_running_loop().call_soon(
            start_task, send_fetches(state), context=Context()
        )
    return response_data(await future)


def response_data(response: Response) -> dict[str, Any]:
    if isinstance(response, Exception):
        raise response
    return response


async def send_first_fetches(state: TransportState) -> None:
    """Send the first fetch of each load when the connection allows it.

    A later fetch of a load, such as the next page, is sent without a wait, so
    that a load with many pages is complete after a few requests (ADR 7). A
    fetch whose entry was dropped, or whose input changed, during the wait is
    not sent.
    """
    loop = asyncio.get_running_loop()
    while (start_at := state.connection.earliest_batch(state.last_batch_at)) > (
        now := loop.time()
    ):
        await asyncio.sleep(start_at - now)
    waiting, state.first_fetches = state.first_fetches, []
    batch = []
    for fetch in waiting:
        if fetch.entry in state.entries and fetch.entry.input == fetch.input:
            batch.append((fetch.query, fetch.future))
        else:
            fetch.future.set_result(_Superseded())
    if batch:
        state.last_batch_at = loop.time()
        await send(state, batch)


async def send_fetches(state: TransportState) -> None:
    batch, state.fetches = state.fetches, []
    await send(state, batch)


async def send(
    state: TransportState, batch: list[tuple[Query, asyncio.Future[Response]]]
) -> None:
    responses = await fetch(state, [query for query, _ in batch])
    for (_, future), response in zip(batch, responses):
        future.set_result(response)


async def fetch(state: TransportState, queries: Sequence[Query]) -> list[Response]:
    try:
        merged = merge(queries)
        body = {"query": merged.document, "variables": merged.variables}
        return merged.split(await state.connection.post(body))
    except Exception as e:
        return [e] * len(queries)


def same_error(a: Exception | None, b: Exception | None) -> bool:
    if a is None or b is None:
        return a is b
    return type(a) is type(b) and str(a) == str(b)


def same(a: Result[Any], b: Result[Any] | None) -> bool:
    return (
        b is not None
        and a.state == b.state
        and a.input == b.input
        and same_error(a.error, b.error)
    )


def deliver(state: TransportState, entry: Entry, result: Result[Any]) -> None:
    if not entry.result.done():
        entry.latest = result
        entry.result.set_result(result)
        if entry.served_pending:
            when_safe_to_nix(replace_result, entry, result)
            return
    elif not same(result, entry.latest):
        when_safe_to_nix(replace_result, entry, result)
        return
    poll_or_reload(state, entry)


def replace_result(entry: Entry, result: Result[Any]) -> None:
    """Keep result for the next load, and nix the old result."""
    entry.latest = result
    entry.fact.nix()


def poll_or_reload(state: TransportState, entry: Entry) -> None:
    """Load again at once if the input changed during the last load, else poll
    when the poll policy says."""
    if entry.loaded_input != entry.input:
        entry.next_poll_at = inf
        enqueue(state, entry)
    else:
        schedule_poll(state, entry)


def schedule_poll(state: TransportState, entry: Entry) -> None:
    assert entry.latest is not None
    now = asyncio.get_running_loop().time()
    delay = entry.poll_policy(entry.latest, now - entry.first_loaded_at)
    entry.next_poll_at = now + state.connection.poll_delay(delay)
    state.changed.set()


async def poll(state: TransportState) -> None:
    """Run each load again when its poll is due, while the window is visible."""
    loop = asyncio.get_running_loop()
    while transports.get(state.transport) is state:
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
