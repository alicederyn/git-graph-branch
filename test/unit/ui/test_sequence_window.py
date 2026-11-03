from collections.abc import Iterator

import pytest
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from git_graph_branch.display import Frame
from git_graph_branch.links import Icon
from git_graph_branch.ui import RowsControl, SequenceWindow

WARNING = "⚠️"
WARNING_X = len("branch ") + 2  # After both columns of 👍


class Rendered:
    def __init__(self, row: StyleAndTextTuples) -> None:
        self.control = RowsControl()
        self.control.frame = Frame([row], None)
        self.window = SequenceWindow(self.control, wrap_lines=False)
        self.screen = Screen()
        self.mouse_handlers = MouseHandlers()

    def render(self) -> None:
        self.window.write_to_screen(
            self.screen,
            self.mouse_handlers,
            WritePosition(0, 0, 40, 1),
            "",
            False,
            None,
        )

    def text(self) -> list[str]:
        line = self.screen.data_buffer[0]
        return [line[x].char for x in range(max(line) + 1)]

    def move_to(self, x: int) -> None:
        self.mouse_handlers.mouse_handlers[0][x](
            MouseEvent(
                Point(x, 0), MouseEventType.MOUSE_MOVE, MouseButton.NONE, frozenset()
            )
        )


@pytest.fixture
def rendered() -> Iterator[Rendered]:
    rendered = Rendered(
        [
            ("", "branch "),
            ("", "👍", Icon(tooltip="approved")),
            ("", WARNING, Icon(tooltip="error")),
            ("", " [1 unmerged]"),
        ]
    )
    app: Application[None] = Application(
        layout=Layout(rendered.window), input=DummyInput(), output=DummyOutput()
    )
    with set_app(app):
        rendered.render()
        yield rendered


def test_a_warning_sign_takes_two_columns(rendered: Rendered) -> None:
    assert rendered.text()[WARNING_X : WARNING_X + 4] == [WARNING, "", " ", "["]
    assert rendered.screen.data_buffer[0][WARNING_X].width == 2


@pytest.mark.parametrize("x", [WARNING_X, WARNING_X + 1])
async def test_both_halves_of_a_warning_sign_show_its_tooltip(
    rendered: Rendered, x: int
) -> None:
    rendered.move_to(x)

    assert rendered.control.hovered is not None
    y, index = rendered.control.hovered
    assert rendered.control.lines[y][index][1] == WARNING
