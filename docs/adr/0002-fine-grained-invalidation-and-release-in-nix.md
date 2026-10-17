# 2. Fine-grained invalidation and release in nix

Date: 2026-10-17

## Status

Proposed

## Decision

We will extend the initial nix MVP to include fine-grained invalidation and
release of in-memory data. nix will track one dependency graph for all data that
a calculation uses, whatever its source. Each piece of data is invalidated when
its source signals a change, or when data it was calculated from is invalidated.
Each piece is released when nothing needs it anymore, and the code that provides
it decides what release means. Sources plug in by giving invalidation signals
and receiving release notices, without changes to the top-level loop or to the
code that reads the data. Filesystem tracking, caching and data from GitHub will
all use this graph.

## Context

nix makes it easy to add active watching to code that reports on many data
sources that change independently, where the data sources that the code reads
change in a complex way, depending on the data that it already read. nix is
based on two observations. First, this kind of logic must be written as
straightforward algorithmic code to stay readable. Second, many data sources
give a signal when their data becomes invalid, but do not push the new data. So
the `git` code does not know about watch mode, and the top-level loop makes only
one decision: `while await needs_refresh(): show(...)`.

The first version of nix calculates everything again each time a signal comes,
because that works well for simple file access. It uses one cohort each time it
calculates the graph. A cohort contains the paths, globs and seen files that the
calculation used. When one of these files changes, the cohort is nixed, and the
`lru_cache` hook clears each cache that the calculation used. The first design
of nix had a goal that was skipped for the first version: a cache that drops
only the entries whose inputs changed.

We now also need data that is not on the filesystem: the check status of pull
requests. This data comes from network I/O, so code must await it. The patched
`Path` methods are synchronous. Many parts of one calculation need this data,
and each request has a cost, so the loads must be coalesced: an async data
loader sends the loads that are made at the same time in one request, and each
calculation awaits its own result.

To keep a cache entry, or to poll a query, after the result that the tool shows
is replaced, nix must know when the new result no longer uses it, for example
after a branch is deleted. This is only known when the calculation of the new
result is complete.

## Alternatives

**One cohort for each calculation.** This is the current design. It is simple,
and it works. We rejected it because each change causes a full recalculation,
and a cache cannot drop only the entries that changed.

**A separate mechanism for network data.** nix keeps the cohort, and adds a
mechanism for network data next to it. This has the smallest refactor risk. We
rejected it because nix would then have two lifecycles, and a cache could still
not drop only the entries that changed.

**Separate types for inputs, computations and the result.** Each type is simpler
than one general kind of data. We rejected it because each type needs its own
rules for invalidation and release, and a cache entry is both an input and a
computation.

**An existing reactive library.** Not decided. A library would give a tested
algorithm. MobX and Meteor Tracker (JavaScript) have similar models. Of the
Python libraries, reaktiv 0.24.2 is the closest match. It records reads through
a context variable, so the existing `Path` and `lru_cache` patches could report
reads to it, and the code outside nix would not change. Its graph is synchronous
and does not create or depend on an event loop, so it works with
`RubiconEventLoop` on macOS. But its computed values are synchronous, so a
calculation cannot await a load inside one. Its `Resource` type gives a
"loading" value, not an awaited result, and it does not batch loads. It gives no
public notice when data is no longer depended upon, and its graph module is not
public API. observ 1.0.1 records reads in a class-level list, not a context
variable, so its tracking does not survive an `await`, and it creates its own
event loop. `shiny.reactive` has a model close to nix, but it is part of the
Shiny web framework package.

**A file bridge.** A poller writes network data to a file, and the filesystem
tracking reads it. nix does not change. We rejected it because it writes
in-process data to disk, and it does not help caching.

## Consequences

nix has one mechanism for all dependencies. Data that was not invalidated can be
reused by the next calculation, so less is calculated again. The code that
provides data is told when it is no longer needed, so it can stop watches and
polls, and limit the size of its cache. A new kind of data does not change the
top-level loop.

This is a refactor of working code, including the platform watchers, which have
had subtle bugs before.

Data can outlive the result that used it, so memory is kept until the code that
provides it releases it.

A calculation can be invalidated while it awaits. The calculation finishes, and
nix at once starts another calculation.

## Confidence

Medium. Filesystem tracking and caching will show if the graph is sufficient,
before data from GitHub uses it.
