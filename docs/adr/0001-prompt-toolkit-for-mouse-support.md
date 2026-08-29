# 1. Use prompt_toolkit for interactive watch mode

Date: 2026-08-29

## Status

Accepted

## Decision

Build mouse interaction in `--watch` mode on prompt_toolkit, awaiting
`Application.run_async()` inside the event loop we already create. Render
branches as formatted-text fragments carrying a `mouse_handler`, so a click
resolves to a `Branch` without any coordinate arithmetic.

Delete `nix/console.py`. prompt_toolkit's diffing renderer supersedes it.

## Context

We want click to select a branch, hover to highlight, and scroll to move the
viewport. Three requirements shape the choice.

1. **A spatial index.** The renderer must know which object is displayed where.
2. **State that survives a refresh.** A filesystem event re-runs
   `compute_branch_dag` and `layout`, which may reorder or drop rows; a selected
   branch must stay selected. Selection and hover reconcile in opposite
   directions — selection follows the object, hover follows the screen position.
3. **Hover degrades gracefully.** Terminals without DEC private mode 1003
   (notably macOS Terminal.app) must lose hover only, keeping click and scroll.

Requirement 3 is nearly free under any option: enable `1000;1002;1003;1006`
unconditionally and a terminal that does not implement 1003 sends no motion
events. Requirement 1 is nearly satisfied already, because `print_branch` emits
exactly one line per branch, so `layout()`'s output list *is* the index.
Requirement 2 is tractable because `Ref.__eq__`/`__hash__` are by ref path, so a
held `Branch` stays value-equal across cache invalidation.

## Alternatives

**Hand-rolled** (`tty.setcbreak`, an SGR parser, line-addressed repaint). Fewer
dependencies, and the flat one-line-per-branch layout means a compositor solves
a problem we do not have. Rejected: it is a few hundred lines of terminal
plumbing — motion coalescing, emoji-aware width measurement, escape sequences
split across reads, mode restoration on exit and crash — that prompt_toolkit has
already debugged across far more terminals than we will test on.

**Textual.** Adds click chains, hover enter/leave and stable row keys.
Rejected as disproportionate: a full application framework for a screen that is
a list of lines.

**urwid.** Rejected: `ListBox` focus is positional, so a reorder moves the
selection, in direct conflict with requirement 2.

**curses.** Rejected: owns output and meshes badly with asyncio.

The objection we expected to decide against prompt_toolkit — that a framework
would insist on owning the event loop and collide with the Rubicon loop driving
the macOS watcher — did not survive investigation. See
[the compatibility note](../notes/rubicon-prompt-toolkit-compatibility.md).
With it gone, the residual risk is shared: every option reads the tty through
`loop.add_reader(0, ...)` and hits the same CoreFoundation path.

## Consequences

`nix/console.py` goes, along with `flush_and_hold_io()` in
`NixLoop.needs_refresh` and the `flush_io_on_shutdown()` wrapper in `watcher()`.
It exists to make a frame atomic, which the diffing renderer provides directly.
It is also actively incompatible: `NixableIO.fileno()` delegates to a `StringIO`
while output is held and raises `io.UnsupportedOperation`, and prompt_toolkit
calls `fileno()` for terminal size and flushing.

`print_branch` returns fragments rather than printing, and lines are truncated
to the terminal width. The golden-output test in
`test/integration/test_entrypoint.py` is the only regression guard over
`display.py` and `cli.py` — neither has unit tests — so its non-interactive path
must be preserved.

Runtime dependencies grow from `ansi` (plus `rubicon-objc` on Darwin) to those
plus `prompt_toolkit` and `wcwidth`. This is a real change for a project that
has stayed close to the standard library, accepted as the cost of not
maintaining a terminal input layer.

## Confidence

High on fit. Moderate on macOS: the compatibility finding rests on reading
`rubicon-objc`, `prompt_toolkit` and Apple's `CFSocket.c`, with no macOS
hardware available to confirm it.

## Revisit if

- prompt_toolkit does not in fact drive stdin on the Rubicon loop on real macOS
  hardware. The fallback is a reader thread feeding a socketpair, which is a
  socket and therefore unambiguously safe for `CFSocketCreateWithNative`.
- Interaction grows beyond a flat list into panes or popups. This reinforces the
  decision, but is the point at which Textual deserves a second look.
