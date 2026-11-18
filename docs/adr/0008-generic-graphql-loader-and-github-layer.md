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
  GitHub layer also records which remote-tracking branches probably came from
  a push from this machine, and changes each loaded state so that it matches the commit of the
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

**The status branch** of a local branch gives its PR status: the branch of the
same name on `remote.pushDefault` if its remote-tracking branch exists, else the
upstream branch if it is on a remote and its remote-tracking branch exists. This
is the rule of the code for
[ADR 5](0005-adaptive-polling-for-pr-check-status.md); the text of ADR 5 does
not give the condition that the remote-tracking branch exists. The GitHub layer
loads the data of the status branch, with the commit of its remote-tracking
branch as the input. When a result was loaded with a different input, the
GitHub layer changes the state that it reads so that it matches the current
input. The loader keeps the state as loaded, so the next load and the poll
policy get it unchanged.

The GitHub layer has a store. Each calculation that gets a PR status reads the
store, also when the branch has no status branch. A read gives the store the
remote-tracking branches and the local branches that exist now. Cached functions
list them from the files under `refs/` and from `packed-refs`. They skip `.lock`
files, count a ref in both places once, and skip `refs/remotes/<remote>/HEAD`,
which is a symbolic ref and not a branch. As the lists are cached, all reads in
one calculation give the same sets.

The store keeps the sets from the last read, and a **just-pushed** set of
remote-tracking branches. On each read:

- A remote-tracking branch that is not in the set from the last read goes into
  the just-pushed set if a local branch with the same name was in the set from
  the last read. A push from this machine usually gives the remote branch the
  name of a local branch that existed before the push. A fetch of the branch of
  another person, followed at once by a checkout, as `gh pr checkout` does, does
  not, as the local branch is new.
- A branch leaves the just-pushed set when the read does not find it, or does
  not find a local branch with its name.
- The first read, and the first read after the store was deleted, puts no
  branch in the just-pushed set.

A second read of the same sets changes nothing. A branch stays in the
just-pushed set after its first read, because `git push -u` changes the
remote-tracking branch before it writes the upstream branch to git config. So a
calculation can find the new remote-tracking branch before it is a status
branch.

The store is a nix fact only so that nix can tell when no calculation reads it;
the store then deletes its data. Nothing nixes the store. Each calculation that
reads it also reads the branches, and a change to them nixes the calculation.

When the status branch is in the just-pushed set, the GitHub layer assumes that
this machine pushed it for the first time, and that it has no PR. For each
branch in the just-pushed set, the store keeps the loads of the status branch
that gave a result, and deletes them when the branch leaves the set. Each of the
three loads of the status branch that has given no result uses a state with no
PR for the current commit while it is pending. When the check load finds an
open PR, the branch leaves the just-pushed set. So a load whose entry is made
again later, for example the merged and closed PRs after a PR closes, shows 🔌
as for other branches. If the first load fails, the GitHub layer shows the error, as
for other branches.

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

**Load the push target before the push.** The push target is the branch that a
push will make, from git config. The GitHub layer loads it with no input; a load
function with no input sends no request and gives no PR. The push then changes
only the input. We rejected it because the status branch must then always be the
push target. So a branch that tracks the PR branch of another person, on a
remote that is not `remote.pushDefault`, does not show that PR until it is
pushed. Also, git config does not name the remote of `git push -u <remote>`.

**Record each push target.** The store keeps one record for each push target,
with whether its remote-tracking branch exists. The push target can be
predicted: `branch.<name>.pushRemote`, else `remote.pushDefault`, else
`origin`, with the name of the local branch. This needs no watch of
`refs/remotes`, and a fetch of a branch with no local branch of the same name
changes nothing. We rejected it because a prediction that is wrong, for example
for `git push -u <remote>` to another remote, shows 🔌, and the rule then has
to follow git's rules for the push remote. The set of remote-tracking branches
follows what the push did.

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
open PR, the PR status shows at once, with no 🔌, if the status branch is on
GitHub and there is a token for it. A branch that was pushed before the first
read of the store shows 🔌, for example a branch pushed while the tool was not
running, or a branch that was made and pushed in one command. A one-shot run waits for each load, so it does not change.

nix now records a state for each file under `refs/remotes`, and watches each
directory. A fetch that changes any remote-tracking branch, also one that no
local branch uses, starts a new calculation. Loads that did not change keep
their results.

The state that the GitHub layer shows can be wrong until a load is complete:

- After a first push, it shows no PR, also if the branch was already on GitHub
  with an open PR. A `git fetch` that makes a remote-tracking branch with the
  name of an existing local branch has the same effect, also if the local branch
  starts to use it later, for example with `git branch -u` after another person
  opened a PR. So does `git remote rename`, for each branch that tracks the
  renamed remote. If the transport delays the first request, for example
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
cannot give it. Or the store must keep more information from git than which
remote-tracking branches probably came from a push.
