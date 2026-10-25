# 7. Queries as async load functions

Date: 2026-10-25

## Status

Proposed

## Decision

A component will give the GraphQL loader
([ADR 4](0004-graphql-loader-with-merged-queries.md)) an async load function,
not one GraphQL document. The loader calls the load function with a `fetch`
function and the state of the previous load. The load function can call `fetch`
more than once, for example to get each page of a connection, and returns the
new state.

The code has three layers:

- **Transport.** `fetch` sends one document. The loader merges all fetches that
  start in the same event-loop tick into one request, as in ADR 4.
- **Facts.** The loader keeps each state as a piece of data in the graph, polls
  again when the poll policy says, and invalidates the state when it changes
  ([ADR 3](0003-async-data-loader.md)).
- **Domain.** The load function contains the knowledge of the GitHub schema:
  which fields to get, how to page, and where to start the next load.

## Context

The review status of a pull request needs its review threads. A pull request
can have more threads than one page gives. If the tool gets only the first page,
the review status is wrong on a large pull request. If the tool tells the user
that the data is not complete, the user cannot do anything about it.

The rate limit cost of a connection depends on the page size, not on the number
of items that GitHub returns. `reviewThreads(first: 100) { comments(first: 1) }`
costs about 100 requests on each poll, even for a pull request with 3 threads.

A `reviewThreads` cursor is `cursor:v2:` followed by a MessagePack array of a
timestamp and a database ID. It is a keyset cursor, not a position. So a cursor
from an earlier poll stays valid when threads are added or deleted, and the
next load can start after the last thread that it does not need again. We
assume that a resolved thread stays resolved. Then each load can start after
the last thread before the oldest unresolved thread.

## Alternatives

**One document for each query, with fixed page sizes.** This is the design of
ADR 4. We rejected it because the result is wrong past the page size, and
because a large page size costs points on each poll.

**Tell the user when a connection has more pages.** We rejected it because the
user cannot do anything about it.

**Paging in the loader.** The loader follows `pageInfo` for the component. We
rejected it because the loader would need to know which connection to follow and
where to start, and that is knowledge of the GitHub schema.

## Consequences

Each load function reads from top to bottom, as a loop over pages. It can be
tested with a fake `fetch`.

The loader keys each entry on the load function, its arguments and the version,
not on the document and its variables.

`MIN_BATCH_INTERVAL` and the rate limit back-off apply when a poll starts. The
next page of a load joins the next batch without a wait, so a load with many
pages shows its result after a few requests, not after a few intervals.

If a page fails, the load gives an error, and the next poll starts from the
state of the last load that did not fail.

If a thread before the stored cursor becomes unresolved again, the tool does
not see it until the tool starts again.

GitHub does not document the cursor format, and can change it. The tool only
stores cursors that GitHub returns, and does not make cursors.

## Confidence

Medium. The cursor format was seen on one pull request.

## Revisit if

GitHub changes `reviewThreads` cursors to positions, or adds a filter for
unresolved threads.
