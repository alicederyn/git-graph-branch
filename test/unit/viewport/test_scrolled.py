from git_graph_branch.viewport import Tracking, Viewport


def test_scrolling_moves_the_window() -> None:
    viewport = Viewport(top=8, tracking=Tracking.STRICT)

    assert viewport.scrolled(-1, head=10, rows=20, height=5).top == 7


def test_scrolling_stops_at_the_first_row() -> None:
    viewport = Viewport(top=1, tracking=Tracking.STRICT)

    assert viewport.scrolled(-5, head=2, rows=20, height=5).top == 0


def test_scrolling_stops_with_the_last_row_at_the_foot_of_the_window() -> None:
    viewport = Viewport(top=14, tracking=Tracking.STRICT)

    assert viewport.scrolled(5, head=15, rows=20, height=5).top == 15


def test_scrolling_with_the_head_row_still_visible_tracks_loosely() -> None:
    viewport = Viewport(top=8, tracking=Tracking.STRICT)

    assert viewport.scrolled(1, head=10, rows=20, height=5) == Viewport(
        top=9, tracking=Tracking.LOOSE
    )


def test_scrolling_the_head_row_off_screen_disables_tracking() -> None:
    viewport = Viewport(top=8, tracking=Tracking.STRICT)

    assert viewport.scrolled(3, head=10, rows=20, height=5) == Viewport(
        top=11, tracking=Tracking.DISABLED
    )


def test_scrolling_the_head_row_back_into_view_tracks_loosely() -> None:
    viewport = Viewport(top=11, tracking=Tracking.DISABLED)

    assert viewport.scrolled(-1, head=10, rows=20, height=5) == Viewport(
        top=10, tracking=Tracking.LOOSE
    )


def test_scrolling_with_a_detached_head_tracks_loosely() -> None:
    viewport = Viewport(top=8, tracking=Tracking.STRICT)

    assert viewport.scrolled(1, head=None, rows=20, height=5) == Viewport(
        top=9, tracking=Tracking.LOOSE
    )
