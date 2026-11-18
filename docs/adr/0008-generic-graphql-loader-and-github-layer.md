# 8. A generic GraphQL loader, and a GitHub layer that uses git

Date: 2026-11-18

## Status

Proposed. Changes parts of ADRs 4, 5 and 7, which are also Proposed.

## Decision

We will split the GraphQL loader ([ADR 4](0004-graphql-loader-with-merged-queries.md))
into two layers.

- **The loader** contains no rules about GitHub or git. It uses nix, batches
  fetches, merges queries, polls, and sends no updates while the window is
  hidden ([ADR 6](0006-no-updates-while-the-window-is-hidden.md)). It groups
  batches by transport, and sends each merged request through it.
- **The GitHub layer** provides the transport: the endpoint, the token, TLS, the
  proxy and the rate limits. The transport compares equal by its endpoint. The
  loader keeps one connection from each transport while it has loads for it,
  and the connection keeps the rate limit state. The connection gives the
  earliest time for the next batch, and can make a poll interval longer. The GitHub layer also changes each loaded state to agree with the
  commit of the remote-tracking branch.

A load has a key and an input. The key identifies the data that the load reads.
The input is a value that the caller reads now, and that the load function
gets. Each result contains the input that its state was loaded with, and a
result with a different input counts as a change. The loader starts each load
function at once. The earliest time for the next batch applies to the first
request of each load, so a load that sends no request is complete at once.
When the input changes, the loader keeps the state, and starts the poll age
again from zero. It loads again at once, or, if a load is running, when that
load is complete. The loader does not decide if a result or the input is newer.

The GitHub layer keys each load on the push target
([ADR 5](0005-adaptive-polling-for-pr-check-status.md)): the branch of the same
name on `remote.pushDefault`, or, if that is not set, the upstream branch if it
is on a remote. The key exists also when the push target has no
remote-tracking branch. The input is the commit of the remote-tracking branch,
or none. With no input, a load function sends no request, and gives a state
that shows no PR, as the PR status does now for a branch with no
remote-tracking branch. When a result was loaded with a different input, the
GitHub layer changes the state that it reads to agree with the current input.
The loader keeps the state as loaded, so the next load and the poll policy get
it unchanged.

## Context

The loader keeps one state for each load
([ADR 7](0007-queries-as-async-load-functions.md)). Since commit 0369eb0, each
entry has a version, and a new version keeps the state. Commit 6f94322 added an
update function, which changes the state when the version changes. The loader
also applies the update to a load that started before the version changed,
because it treats the version as newer than any load that is not complete.
That is true for a push, because GitHub accepts a push before git changes the
remote-tracking branch. It is not always true for a `git fetch`. So the loader
contains a rule about git, and the rule has no reason in the loader.

In `--watch` mode, the version does not help in two cases, and the PR status
shows 🔌 until a load is complete:

- **The first push.** Before the push, the code does not load, so the loader
  has no entry. After the push, the entry is new, with no state.
- **Each push of a branch with no open PR.** The load of merged and closed PRs
  needs the commit of the remote-tracking branch, so the commit is part of its
  key. Each push makes a new entry.

The rate limit code is in the loader because ADR 4 makes the loader the only
code that sends requests to GitHub. So the tests of the loader must fake
GitHub's headers and status codes.

## Alternatives

**Keep the version and the update function, and change the keys.** Key the
loads on the push target before the first push, and move the commit of the
merged and closed PR load from its key to its version. This removes the 🔌 with
less change. We rejected it because the loader keeps the rule about git.

**An initial state for a new entry.** The caller gives a state to use until the
first load is complete. We rejected it because it adds an option to the loader
for one kind of caller. A load function with no input gives the same state.

**Find the first push in the reflog.** A remote-tracking branch whose reflog
has only one entry, "update by push", was created by a push. We rejected it
because git does not document the reflog messages.

**Store information about the world, not states of loads.** The loader keeps
one fact for each piece of information, such as the head of a GitHub branch, and
each load writes the pieces that it gets. A push writes the head, and the newest
write is used. Loads can then use data that other loads got. We rejected it for
now because the loads would share one model of GitHub data, which ADR 4 avoids
for queries, and the layer that keeps facts would contain rules about GitHub,
which ADR 7 keeps in the load functions.

**Compare times.** Each result contains the time its load started, and the
GitHub layer records when it first saw each commit. We rejected it because the
GitHub layer must then keep a record for each entry of the loader, and delete
it when the loader drops the entry. The input of each result gives the same
answer with no record.

## Consequences

This changes parts of earlier ADRs:

- ADR 4: the rate limits and the minimum interval between batches move from the
  loader to the GitHub transport.
- ADR 5: if `remote.pushDefault` is set, the push target is always the branch of
  the same name on that remote. Before this change, a branch with no
  remote-tracking branch on that remote used its upstream branch. So a branch
  that tracks the PR branch of another person, on a remote that is not
  `remote.pushDefault`, no longer shows that PR until it is pushed.
- ADR 7: the loader keys each entry on the transport, the load function and its
  arguments. The load function also gets the input. A load that finishes with
  an old input causes a new load; before this change, the next poll came at the
  interval of the poll policy.

The loader can be tested with no GitHub, and the GitHub layer can be tested
with no loader.

In `--watch` mode, after the first push, and after each push of a branch with no
open PR, the PR status shows at once, with no 🔌. For the first push, this needs
`remote.pushDefault`, because `git push -u` and `push.autoSetupRemote` set the
upstream branch during the push. A one-shot run waits for each load, so it does
not change.

A branch with no remote-tracking branch now has loader entries. They send no
requests. Most branches with an upstream branch but no remote-tracking branch
were pruned after a merge.

The state that the GitHub layer shows after a change of input can be wrong
until the next load is complete:

- After a first push, it shows no PR, also if the branch was already on GitHub
  with an open PR.
- A `git fetch` changes the input as a push does. If GitHub answers a load that
  started before the fetch with data from after it, the GitHub layer still
  changes that data to agree with the fetch.
- If the remote-tracking branch moves from commit A to B and back to A while a
  load runs, the result from A is used as current.

## Confidence

Medium. The split moves working rate-limit code, and the input rules were not
tested in use.

## Revisit if

A component needs data from the load of another component, and the caller
cannot give it. Or the GitHub layer needs local knowledge other than the commit
of a remote-tracking branch.
