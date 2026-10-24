# 4. GraphQL loader with merged queries

Date: 2026-10-17

## Status

Proposed

## Decision

Components will get GitHub data through one GraphQL loader
([ADR 3](0003-async-data-loader.md)) for each GitHub
endpoint. Each component writes its own query. The loader merges the queries of
a batch into one document, with each query as an aliased root field. It uses
`graphql-core` to rewrite the queries.

## Context

Each GraphQL request costs at least one point, even if it asks for very little.
The limit is 5000 points per hour, and all tools that use the same token share
it. Watch mode can run for days.

GitHub calculates points for each call, so the costs of merged queries add
up, but the minimum of one point is paid once for each request. GitHub does not
document a limit on aliases or on root fields. A call can request at most
500,000 nodes. A call that takes more than 10 seconds is ended, and GitHub
deducts extra points for the next hour. github.com and GitHub Enterprise
Server 3.17 reject a JSON array of operations in one request, with 400 "Body
should be a JSON object".

Components must not need to know about the queries of other components. To merge
two queries, the loader must give each query's variables and fragments new
names, so that the names do not collide. A text substitution cannot do this
safely. No Python library merges GraphQL queries into one document. The prior
art is in JavaScript: Gatsby's `merge-queries.js` and the `batch-execute`
package of GraphQL Tools.

The loader is the only code that sends requests to GitHub, so it is also the
place for limits on the request rate
([ADR 5](0005-adaptive-polling-for-pr-check-status.md),
[ADR 6](0006-no-updates-without-focus.md)).

## Open questions

The libraries for the loader are not decided. A prototype of the merge with
`graphql-core` was about 80 lines, and its output passed validation against a
test schema.

**Batching.** A per-tick batcher with a cache was about 40 lines in a tested
prototype, because futures, `loop.call_soon` and a dict do most of the work.
aiodataloader 0.4.3 has 214 lines of code, and the DataLoader of
strawberry-graphql 0.336.0 has 223. The extra lines are for input validation,
batch size limits, priming and clearing the cache, and other options. Both have
a defect when a waiting caller is cancelled, as a load timeout does. In
aiodataloader, the other callers of the same key get `CancelledError`, and so do
later loads of that key. In strawberry, a later load of that key can wait
forever. Both defects were reproduced.

**HTTP.** httpx has had no stable release since 0.28.1 in December 2024.
httpx2 is the continuation by Pydantic, and it uses the trust store of the
operating system. aiohttp is maintained. `urllib` in a thread also works, but a
thread cannot be cancelled, so the timeout must be set on the request. All of
these work on any running asyncio loop, including `RubiconEventLoop`.

**GitHub layer.** githubkit detects primary and secondary rate limits,
including the GraphQL `RATE_LIMITED` error, but it retries automatically by
default and waits until the limit resets, which must be turned off for
[ADR 5](0005-adaptive-polling-for-pr-check-status.md). gidgethub parses the rate
limit headers, but its rate limit handling and retries do not apply to its
GraphQL calls.

## Alternatives

**One request for each component.** This needs no rewrite. We rejected it
because the cost is at least one point for each component on each update.

**One query for all data.** One hand-written query gets everything that the
tool shows. We rejected it because each component would depend on the shape of
one shared query.

**Array batching.** gql can collect requests from a time window and send them
as a JSON array of operations in one request. We rejected it because GitHub
rejects array requests.

**A query DSL.** The DSL of gql can combine aliased root fields that were built
separately. We rejected it because it matches variables by name, so two
components that both use `$owner` share one variable, and because it needs the
schema. sgqlc and ariadne-codegen also need code or types generated from the
schema, and they require `graphql-core` older than 3.3.

**REST with conditional requests.** A `304 Not Modified` response does not use
the rate limit, but GraphQL does not support conditional requests. We rejected
REST because it needs one request for each commit, and a merged GraphQL query
gets the data for all branches in one request.

## Consequences

The cost of an update is for each batch, not for each component. Each query can
be read alone.

GraphQL can return data for some fields and errors for others. The loader gives
each error to the query that caused it, using the alias in the error's `path`.
An HTTP failure fails all loads in the batch. A validation error from the
server has no `path`, so it also fails all loads in the batch. The `locations`
of an error point into the merged document, not into the query of the
component. A null in a non-null root field makes `data` null for all queries in
the batch. A large batch can take more than 10 seconds.

The tool needs a GitHub token. This ADR does not decide how the tool gets it.

The project depends on `graphql-core`.

## Confidence

High.

## Revisit if

GitHub supports conditional requests for GraphQL, or the rate limit stops
counting each request.
