from git_graph_branch.viewport import Tracking, Viewport


def test_strict_centres_the_head_row() -> None:
    assert Viewport().for_render(head=10, rows=20, height=5) == Viewport(
        top=8, tracking=Tracking.STRICT
    )


def test_strict_shows_no_blank_space_above_the_first_row() -> None:
    assert Viewport().for_render(head=1, rows=20, height=5).top == 0


def test_strict_shows_no_blank_space_below_the_last_row() -> None:
    assert Viewport().for_render(head=19, rows=20, height=5).top == 15


def test_rows_shorter_than_the_window_start_at_the_top() -> None:
    assert Viewport().for_render(head=2, rows=3, height=10).top == 0


def test_loose_keeps_the_position_while_the_head_row_is_visible() -> None:
    viewport = Viewport(top=4, tracking=Tracking.LOOSE)

    assert viewport.for_render(head=6, rows=20, height=5) == viewport


def test_loose_recentres_when_a_new_frame_moves_the_head_row_off_screen() -> None:
    viewport = Viewport(top=4, tracking=Tracking.LOOSE)

    assert viewport.for_render(head=12, rows=20, height=5) == Viewport(
        top=10, tracking=Tracking.STRICT
    )


def test_loose_recentres_when_a_resize_moves_the_head_row_off_screen() -> None:
    viewport = Viewport(top=4, tracking=Tracking.LOOSE)

    assert viewport.for_render(head=8, rows=20, height=2) == Viewport(
        top=7, tracking=Tracking.STRICT
    )


def test_disabled_keeps_the_position_while_the_head_row_is_off_screen() -> None:
    viewport = Viewport(top=4, tracking=Tracking.DISABLED)

    assert viewport.for_render(head=12, rows=20, height=5) == viewport


def test_disabled_becomes_loose_when_a_new_frame_shows_the_head_row() -> None:
    viewport = Viewport(top=4, tracking=Tracking.DISABLED)

    assert viewport.for_render(head=6, rows=20, height=5) == Viewport(
        top=4, tracking=Tracking.LOOSE
    )


def test_a_detached_head_leaves_the_tracking_state_alone() -> None:
    for tracking in Tracking:
        viewport = Viewport(top=4, tracking=tracking)

        assert viewport.for_render(head=None, rows=20, height=5) == viewport
