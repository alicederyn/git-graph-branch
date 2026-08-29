# 1. `prompt_toolkit` for mouse support

Date: 2026-08-29

## Status

Accepted

## Decision

We will build mouse support in `--watch` mode using `prompt_toolkit`.

## Context

Any solution must meet two requirements:

1. A refresh must replace the full frame in one step. The user must not see a
   partly drawn frame.
2. The choice of event loop implementation must not be constrained, so that we
   can use features that are specific to an operating system.

Users must be able to scroll the viewport. Without scrolling, the tool is not
usable in small tmux panes. Scrolling adds two more requirements:

3. The renderer must know which branch is on each row. By default, the viewport
   shows the active branch, because that is usually the branch the user cares
   about.
4. The scroll position must survive a refresh. A filesystem event runs
   `compute_branch_dag` and `layout` again, and this can reorder or remove rows.

We may add other mouse features later, such as interacting with branches via
left-click, right-click, or hover. We have not decided on these, but the choice
of library must not prevent them. They extend the scrolling requirements. For
example, if left-click selects a branch, a click must find the branch under the
pointer, and the selection must stay on the same branch after a refresh. Hover
must instead show the branch that is under the pointer after the refresh. Hover
also adds a fifth requirement:

5. On terminals that do not support DEC private mode 1003 (for example, macOS
   Terminal.app), only hover can be missing. Click and scroll must still work.

## Alternatives

Every option meets requirement 5, because a terminal without mode 1003 does not
send motion events.

**`prompt_toolkit`** (chosen). It handles mouse input, character width and
repaint. Its diffing renderer replaces the full frame in one step. It does not
need to own the event loop, because `Application.run_async()` uses the loop that
is already running (see
[the compatibility note](../notes/rubicon-prompt-toolkit-compatibility.md)).
It is lower level than Textual: it does not give click chains, hover enter and
leave events, or stable row keys, so we must build these if we need them. This
work increases if the interface grows beyond a flat list.

**Hand-rolled** (`tty.setcbreak`, an SGR parser, line-addressed repaint). This
adds no dependencies. We rejected it because it needs a few hundred lines of
terminal code: motion event coalescing, emoji width, escape sequences split
across reads, and terminal mode restoration on exit and crash. `prompt_toolkit`
already has this code, and it is tested on more terminals than we can test on.

**Textual.** This gives click chains, hover enter and leave events, and stable
row keys. We rejected it because it is a full application framework, and our
screen is only a list of lines.

**urwid.** We rejected it because `ListBox` focus is by position. When rows
change order, the selection moves to a different branch, but it must stay on the
same branch.

**curses.** We rejected it because it controls all output and does not work well
with asyncio.

## Consequences

Rendering produces formatted-text fragments. A fragment can have a mouse
handler, so a click can find its `Branch` without coordinate calculations.

In watch mode, lines that are wider than the terminal are clipped, with no
marker.

Non-interactive output also goes through `prompt_toolkit`, so its exact bytes
depend on the `prompt_toolkit` version. An upgrade can change the escape
sequences in `--color` output. Plain output uses CRLF line endings, also when it
is redirected.

Watch mode runs as a full-screen application, so a `--pdb` post-mortem session
writes over the alternate screen.

The project depends on `prompt_toolkit`.

## Confidence

High.

## Revisit if

Interaction grows beyond a flat list, for example to panes or popups. We
rejected Textual because the screen is only a list of lines, and that reason
would then no longer apply.
