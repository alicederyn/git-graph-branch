from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import (
    MouseButton,
    MouseEvent,
    MouseEventType,
    MouseModifier,
)

from git_graph_branch.links import Icon


@pytest.fixture(autouse=True)
def open_in_background() -> Iterator[MagicMock]:
    with patch("git_graph_branch.links.open_in_background") as mock:
        yield mock


def click(*modifiers: MouseModifier) -> MouseEvent:
    return MouseEvent(
        position=Point(x=0, y=0),
        event_type=MouseEventType.MOUSE_DOWN,
        button=MouseButton.LEFT,
        modifiers=frozenset(modifiers),
    )


def test_ctrl_click_opens_the_link(open_in_background: MagicMock) -> None:
    assert Icon("https://x")(click(MouseModifier.CONTROL)) is None
    open_in_background.assert_called_once_with("https://x")


def test_plain_click_does_not_open_the_link(open_in_background: MagicMock) -> None:
    assert Icon("https://x")(click()) is NotImplemented
    open_in_background.assert_not_called()


def test_ctrl_click_without_a_url_is_left_to_the_window(
    open_in_background: MagicMock,
) -> None:
    assert Icon(tooltip="tip")(click(MouseModifier.CONTROL)) is NotImplemented
    open_in_background.assert_not_called()
