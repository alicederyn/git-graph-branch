"""Which slice of a row list a window shows, and how scrolling moves it."""

from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import Self


class Tracking(Enum):
    """How closely the viewport follows the current branch."""

    STRICT = auto()
    LOOSE = auto()
    DISABLED = auto()


@dataclass(frozen=True)
class Viewport:
    top: int = 0
    tracking: Tracking = Tracking.STRICT

    def shows(self, row: int, height: int) -> bool:
        return self.top <= row < self.top + height

    def clamped(self, rows: int, height: int) -> Self:
        """Move the window inside the rows, leaving no blank edge."""
        top = max(0, min(self.top, rows - height))
        return replace(self, top=top)

    def centred_on(self, row: int, rows: int, height: int) -> Self:
        return replace(self, top=row - height // 2).clamped(rows, height)

    def for_render(self, head: int | None, rows: int, height: int) -> Self:
        """Position the window for one render.

        A resize changes the height, so this also reconsiders how closely to
        follow the current branch.
        """
        viewport = self.clamped(rows, height)
        if head is not None:
            if viewport.tracking is Tracking.LOOSE and not viewport.shows(head, height):
                viewport = replace(viewport, tracking=Tracking.STRICT)
            elif viewport.tracking is Tracking.DISABLED and viewport.shows(
                head, height
            ):
                viewport = replace(viewport, tracking=Tracking.LOOSE)
            if viewport.tracking is Tracking.STRICT:
                viewport = viewport.centred_on(head, rows, height)
        return viewport

    def scrolled(self, lines: int, head: int | None, rows: int, height: int) -> Self:
        """Move the window by lines, and stop centring the current branch.

        Scrolling the current branch out of the window is taken as a request to
        look elsewhere, so the window stops following it until the branch comes
        back into view.
        """
        viewport = replace(self, top=self.top + lines).clamped(rows, height)
        tracking = (
            Tracking.DISABLED
            if head is not None and not viewport.shows(head, height)
            else Tracking.LOOSE
        )
        return replace(viewport, tracking=tracking)
