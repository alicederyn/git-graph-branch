# 6. No updates without focus

Date: 2026-10-17

## Status

Proposed

## Decision

In `--watch` mode, loaders ([ADR 3](0003-async-data-loader.md))
will send no updates while the pane does not have focus. The tool will get focus
changes from terminal focus reporting (DEC private mode 1004). When the pane
gets focus, the loaders immediately send the updates that are due.

## Context

Watch mode runs for days in tmux panes that nobody looks at. Updates in those
panes use the GitHub rate limit
([ADR 4](0004-graphql-loader-with-merged-queries.md)) and give nothing to the
user.

When focus reporting is on, the terminal sends `CSI I` when the pane gets focus
and `CSI O` when it loses focus. With the tmux option `focus-events on`, tmux
sends these when the user changes pane, window or session, and when the
terminal window gets or loses focus in the OS. `prompt_toolkit` does not parse
these sequences, so we will add them to its `ANSI_SEQUENCES` table, mapped to
keys that we do not otherwise use.

The focus state is not known until the first event. In tmux, the tool gets the
state at startup with `tmux display`. Outside tmux, the tool assumes that it has
focus.

## Alternatives

**Poll tmux for focus.** `tmux display` on a timer, or a tmux control mode
client, also shows focus. We rejected these because focus events are pushed and
need no second connection to tmux.

**Always send updates.** This is simpler. We rejected it because panes that
nobody looks at would use most of the rate limit.

## Consequences

A pane without focus uses none of the rate limit. When the user goes back to
the pane, the data is current after one request.

A pane that is visible but does not have focus, for example in a split, does not
update until it gets focus.

The tool depends on the module-level `ANSI_SEQUENCES` table of
`prompt_toolkit`. An upgrade of `prompt_toolkit` can break focus events.

Without `focus-events on`, the tool never gets focus-out, and sends updates as
if it always has focus. The limits of
[ADR 5](0005-adaptive-polling-for-pr-check-status.md) still apply.

## Confidence

High.

## Revisit if

Users need visible panes without focus to update, or `prompt_toolkit` adds
support for focus events.
