"""Icons that link to a page, opened in the browser on Ctrl+left-click, or show
a tooltip on hover."""

import webbrowser
from dataclasses import dataclass
from typing import TYPE_CHECKING

from prompt_toolkit.mouse_events import (
    MouseButton,
    MouseEvent,
    MouseEventType,
    MouseModifier,
)

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone


def open_in_background(url: str) -> None:
    """Open url, unless the only browser runs in the terminal.

    webbrowser falls back to a console browser such as lynx when there is no
    display, and it would take over the terminal and block the event loop.
    """
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return
    if type(browser) is webbrowser.GenericBrowser:
        return
    browser.open(url)


@dataclass(frozen=True)
class Icon:
    """The mouse handler of an icon fragment.

    The tooltip is shown by RowsControl, as it needs the pointer position.
    """

    url: str | None = None
    tooltip: str | None = None

    def __call__(self, mouse_event: MouseEvent) -> "NotImplementedOrNone":
        if (
            self.url
            and mouse_event.event_type == MouseEventType.MOUSE_DOWN
            and mouse_event.button == MouseButton.LEFT
            and MouseModifier.CONTROL in mouse_event.modifiers
        ):
            open_in_background(self.url)
            return None
        return NotImplemented
