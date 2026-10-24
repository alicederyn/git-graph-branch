# 6. No updates while the window is hidden

Date: 2026-10-24

## Status

Proposed

## Decision

In `--watch` mode, loaders ([ADR 3](0003-async-data-loader.md)) will send no
updates while no tmux client shows the window of the tool's pane. The tool will
get changes from a tmux control-mode client that is attached to a session that
the tool creates for itself. When the window becomes visible, the loaders
immediately send the updates that are due. Outside tmux, the tool assumes that
the window is visible.

## Context

Watch mode runs for days in tmux windows that nobody looks at. Updates in those
windows use the GitHub rate limit
([ADR 4](0004-graphql-loader-with-merged-queries.md)) and give nothing to the
user. The goal is about one active tool for each user, not one for each window.

The format `#{window_active_clients_list}` gives the clients that show a window.
`tmux display -p -t "$TMUX_PANE"` gets it for the tool's pane.

A control-mode client (`tmux -C`) gets notifications. A test on tmux 3.4 showed
that a control client gets these notifications for sessions that it is not
attached to:

- `%session-window-changed` when a session changes its active window.
- `%client-detached` when a client detaches.
- `%client-session-changed` when a client attaches to a session.

The tool queries the format at startup and after each of these notifications.
The control client shows only the window of its own session, so it is never in
the list.

A control client counts as an attached client. When `tmux attach` has no
target, tmux prefers the most recently used unattached session. If the control
client attaches to the user's session, `tmux attach` can then select a
different session. The tool's own session has `destroy-unattached on`, so tmux
removes it when the tool exits, also after a crash.

A pane can be hidden in a visible window when another pane is zoomed. The tool
ignores this case.

## Alternatives

**Terminal focus reporting.** DEC private mode 1004 sends `CSI I` and `CSI O`
when the pane gets and loses focus. We rejected it because focus is not
visibility. A pane in a split loses focus when the user selects the other pane,
but it is still visible.

**Poll `tmux display` on a timer.** This needs no second connection to tmux. We
rejected it because the tool would run tmux every few seconds for days in
windows that nobody looks at. A poll only while an update is due has the same
problem: when the window is hidden, an update stays due.

**A control client attached to the user's session.** This needs no extra
session. We rejected it because it changes which session `tmux attach` selects.

**A `refresh-client -B` subscription.** tmux sends `%subscription-changed` when
the value of a format changes, so the tool would need no query. We rejected it
because a subscription to a pane in another session gave no output in a test.

**tmux hooks.** `set-hook` can run a command when the active window changes. We
rejected it because the hooks change the user's global tmux configuration, and
the tool must remove them on exit.

**Always send updates.** This is simpler. We rejected it because windows that
nobody looks at would use most of the rate limit.

## Consequences

A hidden window uses none of the rate limit. When the user goes back to the
window, the data is current after one request.

A visible window with no focus, for example in a split, updates.

The tool's session shows in `tmux ls` and `choose-tree` while the tool runs.

A window that a tmux client shows, in a terminal window that is minimized or
behind another window, counts as visible.

The tool depends on control-mode notifications that the tmux man page does not
document for sessions that the client is not attached to.

## Confidence

High.

## Revisit if

tmux adds a way to watch other sessions without an attached client, or users
need hidden windows to update.
