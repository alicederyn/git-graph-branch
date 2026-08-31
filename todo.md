# Todo

Deferred work, for later prioritization. Found while moving rendering onto
prompt_toolkit (ADR 0001); none of it is part of that change.

## Rendering

- **Truncate overlong lines with an ellipsis in watch mode.**
  `Window(wrap_lines=False)` clips only. prompt_toolkit has no
  truncate-to-width helper for fragment lists, so this needs a
  `FormattedTextControl` subclass overriding `create_content(width, height)`,
  plus a wcwidth-aware cut (`fragment_list_width`) because 🔶 🔷 🌲 are two
  cells wide.
- **`--pdb` under a full-screen app.** `pdb.post_mortem` writes over the
  alternate screen. It needs `run_in_terminal`, or the app must exit first.
- **Colour choice.** The "safe to delete" grey is SGR 37, which is nearly
  invisible on a light background. `ui.STYLE` now makes this changeable in one
  place.
- **`docs/repo-screenshot.png`, `docs/key.png`.** Regenerate if watch mode's
  appearance changes.

## Dead code

- `cli.optional_to_iterable` — no callers.
- `cli.LOG` — never used.
- `log_config.configure_logging` — never called.

## `display.Config`

- `__init__` does `super().__init__(**(kwargs | defaults), is_tty=is_tty)`, so
  `defaults` wins over `kwargs`. `Config(is_tty=False, color=True)` silently
  yields `color=False`. Harmless today because `parse_args` passes no other
  kwargs, but a trap for new tests.
- `pdb` is set on `Config` by argparse but is not declared on the class.

## Test coverage

- No unit tests for `parse_args`. `--watch` and `--poll-every` are registered
  only when `is_tty`, so the non-TTY tests cannot reach them.
- `layout()` has no direct test; only `partially_ordered` and `add_node_art`.
- **Nothing asserts that watch mode refreshes.** `test_watch_ui.py` covers only
  the first frame. A test that touches a ref and waits for the display to change
  would depend on inotify delivery, the coalescing latency in `nix/linux.py` and
  mtime granularity against `SAFETY_MARGIN`.
- **The console script in `[project.scripts]` is untested.**
  `test_watch_ui.py` runs `main()` through `python -c`, so a broken entry point
  declaration would go unnoticed. Testing it ties the suite to the install state
  of the venv.

## `nix`

- **A cached call outside a nix context manager does not raise.**
  `install()` patches `functools.lru_cache` for every module imported after it,
  so `wcwidth` and any other third-party cache would trip the guard. Restricting
  the check to `user_function.__module__` inside `git_graph_branch` would restore
  it, at the cost of sniffing module names.
- `tracking.paths_in_cohort` iterates `cohort.globs` while the patched `glob`
  adds to that same set. It survives only because `Glob` is frozen, so the added
  value equals the existing one and the set never grows.

## Git internals

- `display.remote_sync_status` carries an existing TODO: check whether the
  upstream commit is an ancestor of the branch commit, not just older.
