"""Monitors the filesystem for changes.

Monkeypatches common libraries to track filesystem access and data caching,
allowing filesystem monitoring to be implemented orthogonally to the
main logic of the program.

Usage:
    from git_graph_branch import nix

    # Before doing any other imports
    nix.install()

    async with nix.watcher(poll_every=timedelta(seconds=1)) as needs_refresh:
        while await needs_refresh():
            # Do I/O-based logic
"""

from .loop import once, watcher
from .patching import install

__all__ = ["install", "watcher", "once"]
