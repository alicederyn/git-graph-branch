# 8. A generic GraphQL loader, and a GitHub layer that uses git

Date: 2026-11-18

## Status

Proposed. Changes parts of ADRs 4 and 7, which are also Proposed.

## Decision

We will split the GraphQL loader
([ADR 4](0004-graphql-loader-with-merged-queries.md)) into two layers.

- **The loader** contains no rules about GitHub or git. It uses nix, batches
  fetches, merges queries, polls, and sends no updates while the window is
  hidden ([ADR 6](0006-no-updates-while-the-window-is-hidden.md)). It groups
  batches by transport, and sends each merged request through it.
- **The GitHub layer** provides the transport: the endpoint, the token, TLS, the
  proxy and the rate limits. The transport compares equal by its endpoint. The
  loader keeps one connection from each transport while it has loads for it,
  and the connection keeps the rate limit state. The connection gives the
  earliest time for the next batch, and can make a poll interval longer. The
  GitHub layer also records whether each push target had a remote-tracking
  branch, and changes each loaded state so that it matches the commit of the
  remote-tracking branch.

A load has a key and an input. The key identifies the data that the load reads.
The input is a value that the caller reads now, and that the load function
gets. Each result contains the input that its state was loaded with, and a
result with a different input counts as a change. The loader starts each load
function at once. The earliest time for the next batch applies to the first
request of each load, so a load that sends no request is complete at once.
When the input changes, the loader keeps the state, and starts the poll age
again from zero. It loads again at once, or, if a load is running, when that
load is complete. The loader does not decide if a result or the input is newer.

The GitHub layer uses two branches for each local branch:

- **The status branch** gives the PR status: the branch of the same name on
  `remote.pushDefault` if its remote-tracking branch exists, else the upstream
  branch if it is on a remote and its remote-tracking branch exists. This is
  the rule of the code for
  [ADR 5](0005-adaptive-polling-for-pr-check-status.md); the text of ADR 5 does
  not give the condition that the remote-tracking branch exists. The GitHub
  layer loads the data of the status branch, with the commit of its
  remote-tracking branch as the input. When a result was loaded with a
  different input, the GitHub layer changes the state that it reads so that it
  matches the current input. The loader keeps the state as loaded, so the next
  load and the poll policy get it unchanged.
- **The push target** is the branch that git config names, whether its
  remote-tracking branch exists or not: the branch of the same name on
  `remote.pushDefault`, else the upstream branch if it is on a remote. When the
  remote-tracking branch of the push target exists, the push target is also the
  status branch.

The GitHub layer has a store, with one record for each push target on GitHub,
keyed on the git remote and the branch name.
When it gets the PR status of a branch, it reads the record of the branch's push
target, also before the push, and also when the status branch is the upstream
branch. A record is a nix fact only so that the store deletes it when no
calculation reads it. Each read changes the record from what the read finds:

- **Absent:** the read found no remote-tracking branch.
- **Pushed:** the record was absent or pushed, and the read found a
  remote-tracking branch. The GitHub layer assumes that this machine pushed the
  branch for the first time, and that the branch has no PR.
- **Present:** the record was missing or present, and the read found a
  remote-tracking branch. The GitHub layer assumes nothing.

A second read with the same remote-tracking branch gives the same state, so the
checks, the reviews, and the merged and closed PRs read the same state in one
calculation, and a calculation that runs again reads it again with no change.
Nothing nixes a record: each calculation that reads it also reads the
remote-tracking branch, and a change of that branch nixes the calculation.

While the record is pushed, each of the three loads of the status branch that
has given no result since the push uses a state with no PR for the current
commit while it is pending. The record keeps the loads that gave a result, so a
load whose entry is made again later, for example the merged and closed PRs
after a PR closes, shows 🔌 as for other branches. If the first load fails, the
GitHub layer shows the error, as for other branches.

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

**Show 🔌 after a first push.** This needs no store. We rejected it because the
tool shows that it does not know, when git makes it probable that there is no
PR.

**Keep the version and the update function, and change the keys.** Move the
commit of the merged and closed PR load from its key to its version. This
removes the 🔌 after later pushes with less change. We rejected it because the
loader keeps the rule about git.

**An initial state for a new entry.** The caller gives the loader a state to use
until the first load is complete. We rejected it because it adds an option to
the loader for one kind of caller. The GitHub layer gives the same state when it
reads a pending result.

**Load the push target before the push.** The GitHub layer loads the push
target with no input, and a load function with no input sends no request and
gives no PR. The push then changes only the input. We rejected it because the
status branch must then always be the push target. So a branch that tracks the
PR branch of another person, on a remote that is not `remote.pushDefault`, does
not show that PR until it is pushed.

**Find the first push in the reflog.** A remote-tracking branch whose reflog
has only one entry, "update by push", was created by a push. We rejected it
because git does not document the reflog messages.

**Store information about the world, not states of loads.** The store keeps one
fact for each item of information, such as the head of a GitHub branch, and each
load writes the items that it gets. A push writes the head, and the newest write
is used. We rejected it for now because the loads would share one model of
GitHub data, which ADR 4 avoids for queries. The store keeps only the
information that no query gives.

**Compare times.** Each result contains the time its load started, and the
GitHub layer records when it first saw each commit. We rejected it because the
input of each result gives the same answer, and the store would then need a
record for each commit.

## Consequences

This changes parts of earlier ADRs:

- ADR 4: the rate limits and the minimum interval between batches move from the
  loader to the GitHub transport.
- ADR 7: the loader keys each entry on the transport, the load function and its
  arguments. The load function also gets the input. A load that finishes with
  an old input causes a new load; before this change, the next poll came at the
  interval of the poll policy.

The loader can be tested with no GitHub, and the GitHub layer can be tested
with no loader.

In `--watch` mode, after the first push, and after each push of a branch with no
open PR, the PR status shows at once, with no 🔌. For the first push, this needs
the push target in git config before the push: in practice `remote.pushDefault`,
or an upstream branch whose remote-tracking branch was pruned. Without
`remote.pushDefault`, the push target before a first push is usually an
upstream branch such as `origin/main`, which exists, and `git push -u` and
`push.autoSetupRemote` set the upstream branch only during the push. A branch
that a calculation did not read before its first push, for example because the
branch was made and pushed in one command, or while the tool was not running,
shows 🔌. A one-shot run waits for each load, so it does not change.

The state that the GitHub layer shows can be wrong until a load is complete:

- After a first push, it shows no PR, also if the branch was already on GitHub
  with an open PR. A `git fetch` that makes the remote-tracking branch appear
  has the same effect. If the transport delays the first request, for example
  until a rate limit ends, this state shows for that time. The repository's
  default branch is not known, so a first push of a branch with that name shows
  a link to make a PR.
- A `git fetch` changes the input as a push does. If GitHub answers a load that
  started before the fetch with data from after it, the GitHub layer still
  changes that data to match the fetch.
- If the remote-tracking branch moves from commit A to B and back to A while a
  load runs, the result from A is used as current.

## Confidence

Medium. The split moves working rate-limit code, and the input rules were not
tested in use.

## Revisit if

A component needs data from the load of another component, and the caller
cannot give it. Or the store must keep more information from git than the three
states of a push target.
