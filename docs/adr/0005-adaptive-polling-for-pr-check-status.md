# 5. Adaptive polling for PR check status

Date: 2026-10-17

## Status

Proposed

## Decision

We will show the check status of each branch's pull request as an emoji. In
`--watch` mode, the GraphQL loader
([ADR 4](0004-graphql-loader-with-merged-queries.md)) will poll for updates.
The interval depends on how probable a change is: fast for a few minutes after
the head of a pull request changes, medium while a check is not final, and slow
when all checks are final. If the main branch has no checks, we will use only
the slow interval.

## Context

GitHub does not push check status to clients. The GraphQL API has no
subscriptions, on github.com or on GitHub Enterprise Server. Webhooks need an
HTTP endpoint that GitHub can reach, and a terminal tool on a workstation does
not have one. The REST Events API is also polled, has a latency of minutes, and
does not contain check events.

A fixed interval cannot meet both of our needs. When the user waits for checks,
results must show quickly. When nothing changes, polls must use little of the
rate limit.

GraphQL has no reliable push time, because `Commit.pushedDate` is deprecated
and returns null. But the local head SHA is part of the query variables, so
after a push from this machine the tool loads a different result, and the
loader fetches it immediately
([ADR 3](0003-async-data-loader.md)). For a few minutes after
the push, the new head has no checks because CI has not registered them yet. In
a repository with no checks, this state does not end, so the fast interval must
end after a fixed time. The tool loads the checks of the main branch at startup,
so it knows early if the repository has checks.

BBGitHub enforces hourly rate limits, and its automation policy asks for
sequential requests without bursts. The policy's rule against polling applies to
integrations, and this tool is not one. GitHub also has secondary limits: at
most 2,000 points per minute and 100 concurrent requests. When the hourly limit
is used up, the response status is still 200, with `x-ratelimit-remaining: 0`.

The loader never sends a batch sooner than a fixed minimum interval after the
last batch. When `rateLimit.remaining` is low, it uses the slow interval until
`resetAt`. At a 5 s minimum and about one point per batch, the worst case is
720 points per hour, which is less than the limit.

## Alternatives

**Webhooks through a relay service.** This gives push events. We rejected it
because we would have to operate a service that GitHub can reach.

**Fixed-interval polling.** This is simpler. We rejected it because a short
interval uses too much of the rate limit when nothing changes, and a long
interval shows results late when the user waits for them.

## Consequences

Check results show a few seconds after they change, while the user waits for
them. A repository where nothing changes uses only a few points per hour.

Pushes from other machines, and checks that are run again from the web UI, show
after one slow interval at most.

If the main branch has no checks but a pull request has checks, the first
results for that pull request show late. After that, the normal intervals
apply.

The intervals are estimates, and we will tune them.

## Confidence

Medium.

## Revisit if

GitHub adds a push channel that does not need an endpoint that GitHub can reach.
