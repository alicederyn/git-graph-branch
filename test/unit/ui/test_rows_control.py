from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType

from git_graph_branch.display import Frame
from git_graph_branch.ui import RowsControl

WIDTH = 80


def frame(rows: int, head: int | None) -> Frame:
    return Frame([[("", f"branch{i}")] for i in range(rows)], head)


def visible(control: RowsControl, height: int) -> list[str]:
    content = control.create_content(WIDTH, height)
    lines: list[StyleAndTextTuples] = [
        content.get_line(i) for i in range(content.line_count)
    ]
    return [fragment[1] for line in lines for fragment in line]


def wheel(event_type: MouseEventType) -> MouseEvent:
    return MouseEvent(
        position=Point(x=0, y=0),
        event_type=event_type,
        button=MouseButton.NONE,
        modifiers=frozenset(),
    )


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
    """The head row was visible before the frame, so rule 6 applies."""
    control = RowsControl()
    control.frame = frame(rows=10, head=5)
    visible(control, height=3)
    control.scroll(1)

    control.frame = frame(rows=10, head=9)

    assert visible(control, height=3) == ["branch7", "branch8", "branch9"]


def test_the_whole_content_is_offered_when_no_height_is_given() -> None:
    control = RowsControl()
    control.frame = frame(rows=10, head=5)

    assert control.create_content(WIDTH, None).line_count == 10
