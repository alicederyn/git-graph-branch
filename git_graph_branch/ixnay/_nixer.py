from __future__ import annotations

from typing import Protocol


class Nixer(Protocol):
    def nix(self) -> None:
        """Nix (invalidate) a previously-returned result attached to this Nixer.

        This method should only be called from the asyncio event loop.
        """
        ...

    @property
    def is_active(self) -> bool:
        """Whether nixing is active.

        Used to avoid paying the cost of nix logic if a result will only be used once.
        """
        ...


class SingleUseNixer(Nixer):
    def nix(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return False
