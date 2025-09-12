"""Monitors the filesystem for changes.

Monkeypatches common libraries to track filesystem access and data caching,
allowing filesystem monitoring to be implemented orthogonally to the
main logic of the program.

Usage:
    import asyncio
    from git_graph_branch import nix

    # Before doing any other imports
    nix.install()

    async def amain() -> None:
        async with nix.watcher(poll_every=timedelta(seconds=1)) as needs_refresh:
            while await needs_refresh():
                # Do I/O-based logic

    asyncio.run(amain(), loop_factory=nix.loop_factory)
"""

from .loop import loop_factory, once, watcher
from .patching import install

__all__ = ["install", "loop_factory", "once", "watcher"]
