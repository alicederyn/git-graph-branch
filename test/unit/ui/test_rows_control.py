import asyncio
from typing import TYPE_CHECKING

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType

from git_graph_branch.display import Frame
from git_graph_branch.links import Icon
from git_graph_branch.ui import RowsControl, padded_tooltip

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone

WIDTH = 80
LINK_X = len("branch ")


def frame(rows: int, head: int | None) -> Frame:
    return Frame([[("", f"branch{i}")] for i in range(rows)], head)


def visible(control: RowsControl, height: int) -> list[str]:
    content = control.create_content(WIDTH, height)
    lines: list[StyleAndTextTuples] = [
        content.get_line(i) for i in range(content.line_count)
    ]
    return [fragment[1] for line in lines for fragment in line if fragment[1] != " "]


def wheel(event_type: MouseEventType) -> MouseEvent:
    return MouseEvent(
        position=Point(x=0, y=0),
        event_type=event_type,
        button=MouseButton.NONE,
        modifiers=frozenset(),
    )


def click(x: int, y: int = 0) -> MouseEvent:
    return MouseEvent(
        position=Point(x=x, y=y),
        event_type=MouseEventType.MOUSE_DOWN,
        button=MouseButton.LEFT,
        modifiers=frozenset(),
    )


class Handler:
    def __init__(self) -> None:
        self.events: list[MouseEvent] = []

    def __call__(self, mouse_event: MouseEvent) -> "NotImplementedOrNone":
        self.events.append(mouse_event)
        return None


def linked_frame(*handlers: Handler) -> Frame:
    return Frame([[("", "branch "), *(("", "👍", h) for h in handlers)]], 0)


def test_the_window_is_centred_on_the_head_branch() -> None:
    control = RowsControl()
    control.frame = frame(rows=10, head=5)

    assert visible(control, height=3) == ["branch4", "branch5", "branch6"]


def test_the_wheel_moves_the_window() -> None:
    control = RowsControl()
    control.frame = frame(rows=10, head=5)
    visible(control, height=3)

    control.mouse_handler(wheel(MouseEventType.SCROLL_DOWN))

    assert visible(control, height=3) == ["branch5", "branch6", "branch7"]


def test_an_unhandled_mouse_event_is_left_to_the_window() -> None:
    control = RowsControl()

    assert control.mouse_handler(wheel(MouseEventType.MOUSE_DOWN)) is NotImplemented


def test_the_keyboard_moves_the_window_to_either_end() -> None:
    control = RowsControl()
    control.frame = frame(rows=10, head=5)
    visible(control, height=3)

    control.to_bottom()
    assert visible(control, height=3) == ["branch7", "branch8", "branch9"]

    control.to_top()
    assert visible(control, height=3) == ["branch0", "branch1", "branch2"]


def test_a_page_is_one_window() -> None:
    control = RowsControl()
    control.frame = frame(rows=20, head=0)
    visible(control, height=4)

    control.scroll_pages(1)

    assert visible(control, height=4) == [
        "branch4",
        "branch5",
        "branch6",
        "branch7",
    ]


def test_a_new_frame_holds_a_scrolled_position() -> None:
    control = RowsControl()
    control.frame = frame(rows=10, head=5)
    visible(control, height=3)
    control.scroll(3)

    control.frame = frame(rows=10, head=4)

    assert visible(control, height=3) == ["branch7", "branch8", "branch9"]


def test_a_new_frame_recentres_a_head_branch_that_scrolls_away() -> None:
    """The scroll left the head row in view, so the window still follows it."""
    control = RowsControl()
    control.frame = frame(rows=10, head=5)
    visible(control, height=3)
    control.scroll(1)

    control.frame = frame(rows=10, head=9)

    assert visible(control, height=3) == ["branch7", "branch8", "branch9"]


def test_a_click_on_a_link_goes_to_its_handler() -> None:
    """Window gives the control a character index, not a screen column, so the
    second icon is one character after the first, though the first is two
    columns wide."""
    first, second = Handler(), Handler()
    control = RowsControl()
    control.frame = linked_frame(first, second)
    control.create_content(WIDTH, 1)

    event = click(LINK_X + 1)

    assert control.mouse_handler(event) is None
    assert (first.events, second.events) == ([], [event])


@pytest.mark.parametrize(
    "position",
    [click(0), click(LINK_X + 1), click(0, y=1)],
    ids=["other text", "end of row", "below the rows"],
)
def test_a_click_off_a_link_is_left_to_the_window(position: MouseEvent) -> None:
    """Window gives a click right of a row to the row's last character, and a
    click below the rows to the last row."""
    control = RowsControl()
    control.frame = linked_frame(Handler())
    control.create_content(WIDTH, 2)

    assert control.mouse_handler(position) is NotImplemented


DELAY = 0.01


def move(x: int, y: int = 0) -> MouseEvent:
    return MouseEvent(
        position=Point(x=x, y=y),
        event_type=MouseEventType.MOUSE_MOVE,
        button=MouseButton.NONE,
        modifiers=frozenset(),
    )


def tooltip_frame(*tooltips: str) -> Frame:
    return Frame(
        [[("", "branch "), *(("", "👍", Icon(tooltip=t)) for t in tooltips)]], 0
    )


def hovering_control(frame: Frame) -> RowsControl:
    control = RowsControl(tooltip_delay=DELAY)
    control.frame = frame
    control.create_content(WIDTH, 1)
    control.mouse_handler(move(LINK_X))
    return control


async def test_a_tooltip_shows_at_the_pointer_after_the_delay() -> None:
    control = hovering_control(tooltip_frame("tip"))
    assert control.tooltip is None

    await asyncio.sleep(DELAY * 5)

    assert control.tooltip == "tip"
    assert control.create_content(WIDTH, 1).menu_position == Point(x=LINK_X, y=0)


async def test_a_move_inside_the_icon_keeps_the_delay() -> None:
    control = hovering_control(tooltip_frame("tip"))
    timer = control.tooltip_timer

    control.mouse_handler(move(LINK_X))

    assert control.tooltip_timer is timer


@pytest.mark.parametrize(
    "position", [move(0), move(LINK_X + 1)], ids=["off the icon", "to another icon"]
)
async def test_a_move_off_the_icon_hides_the_tooltip(position: MouseEvent) -> None:
    control = hovering_control(tooltip_frame("tip", "other"))
    await asyncio.sleep(DELAY * 5)

    control.mouse_handler(position)

    assert control.tooltip is None


async def test_a_new_frame_shows_the_tooltip_now_under_the_pointer() -> None:
    control = hovering_control(tooltip_frame("tip"))
    await asyncio.sleep(DELAY * 5)

    control.frame = tooltip_frame("new tip")
    control.create_content(WIDTH, 1)

    assert control.tooltip == "new tip"


async def test_a_new_frame_with_no_icon_under_the_pointer_hides_the_tooltip() -> None:
    control = hovering_control(tooltip_frame("tip"))
    await asyncio.sleep(DELAY * 5)

    control.frame = frame(rows=1, head=0)
    control.create_content(WIDTH, 1)

    assert control.tooltip is None


def test_a_tooltip_wraps_between_words_to_fit_the_window() -> None:
    assert padded_tooltip("origin: 2 ahead\nupstream: 1 behind", 12) == (
        " origin: 2 \n ahead \n upstream: \n 1 behind "
    )
