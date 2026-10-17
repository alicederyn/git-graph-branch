# 3. Async data loader

Date: 2026-10-17

## Status

Proposed

## Decision

We will get data from network services through async data loaders that use the
dependency graph of
[ADR 2](0002-fine-grained-invalidation-and-release-in-nix.md). Code awaits each
load. A loader sends all loads that start in the same event-loop tick to its
source in one request, and keeps each result as a piece of data in the graph.
In `--watch` mode, the loader gets updates from the source in the background,
and invalidates a result when it changes. When a result is released, the loader
stops getting updates for it.

## Context

The first data from a network service is the check status of pull requests,
from the GitHub GraphQL API. Many parts of one calculation need this data, for
example one load for each branch. Each request costs part of a rate limit that
all tools that use the same token share.

The code that uses the data must not need code for watch mode, as with the
`git` code. A one-shot run and a watch-mode run must use the same code.

GitHub does not push changes to clients, so the loader must poll for them.

## Alternatives

**A pending value.** A load that is not cached returns "no data yet", and the
result invalidates the calculation when it arrives. This needs no async code. We
rejected it because each part of the code must handle a value that has no
meaning, and a one-shot run would show a result with no network data.

**One request for each load.** This needs no batching. We rejected it because
each request costs part of the rate limit, even if it asks for very little.

## Consequences

The code that calculates the graph becomes async. The `git` code stays
synchronous.

Loads that wait for each other are not batched. Code that needs several loads
must start them together, for example with `asyncio.gather`.

A one-shot run waits for the network before it shows the graph. In watch mode,
the first result waits for the first request. Loads need a timeout, so that a
machine with no network still shows a result. A load that fails gives an error,
and the code shows it.

On macOS, the event loop is `RubiconEventLoop`, which has no loop iteration.
Each scheduled callback is its own timer, and the timers run in the order they
were scheduled. So "the same event-loop tick" means "before the loader's
dispatch callback runs". This has not been tested on macOS.

Async functions cannot use `@cache`, because the cache would store the
coroutine, and a second `await` of a coroutine raises an error.

## Confidence

High. Batching the loads of one event-loop tick is a known pattern (DataLoader).
