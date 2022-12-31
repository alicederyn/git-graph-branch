# coding=utf-8
from __future__ import annotations

from textwrap import dedent

from git_graph_branch.dag import NodeArt


def test_row_repr() -> None:
    assert repr(NodeArt(2)) == "NodeArt(at = 2)"
    assert repr(NodeArt(2, up=range(3))) == "NodeArt(at = 2, up = {0,1,2})"
    assert (
        repr(NodeArt(0, down=(1,), through=(2, 4)))
        == "NodeArt(at = 0, down = {1}, through = {2,4})"
    )


def test_row_unicode() -> None:
    assert str(NodeArt(2)) == "    ─"
    assert str(NodeArt(0, up={0}, down={0})) == "┼"
    assert str(NodeArt(0, down={0})) == "┬"
    assert str(NodeArt(0, up={0})) == "┴"
    assert str(NodeArt(1, up={0}, down={0})) == "├▶╴"
    assert str(NodeArt(4, up={4}, down={1, 2, 3, 4})) == "  ┌─┬─┬▶┼"
    assert str(NodeArt(4, up={4}, down={0, 4}, through={1, 2, 3})) == "┌┄│┄│┄│▶┼"
    assert str(NodeArt(0, up={0}, down={0}, through={1, 2, 3, 4})) == "┼ │ │ │ │"
    assert str(NodeArt(4, up={4}, down={1, 3, 4}, through={2, 5})) == "  ┌┄│┄┬▶┼ │"
    assert str(NodeArt(2, up={0, 1, 2, 3, 4}, down={0, 1, 2, 3, 4})) == "├─┼▶┼◀┼─┤"
    assert str(NodeArt(0, down={0, 1})) == "┬◀┐"


def test_row_equality() -> None:
    assert NodeArt(2) == NodeArt(2)
    assert NodeArt(2) != NodeArt(2, up={4})


def test_row_max_min_cols() -> None:
    assert NodeArt(2)._min == 2
    assert NodeArt(2)._max == 2
    assert NodeArt(2)._cols == 3
    assert NodeArt(2, up={3, 4}, down={0, 1})._min == 0
    assert NodeArt(2, up={3, 4}, down={0, 1})._max == 4
    assert NodeArt(2, up={3, 4}, down={0, 1})._cols == 5
    assert NodeArt(2, through={1, 5})._min == 2
    assert NodeArt(2, through={1, 5})._max == 2
    assert NodeArt(2, through={1, 5})._cols == 6


def test_row_unicode_branch_merge_to_head() -> None:
    grid = [
        NodeArt(at=0, down=[0]),
        NodeArt(at=0, up=[0], down=[0]),
        NodeArt(at=0, up=[0], down=[0]),
        NodeArt(at=0, up=[0], down=[0]),
        NodeArt(at=0, up=[0], down=[0]),
        NodeArt(at=0, up=[0], down=[0]),
        NodeArt(at=0, up=[0], down=[0, 1, 2, 3]),
        NodeArt(at=0, up=[0], down=[0, 4], through=[1, 2, 3]),
        NodeArt(at=0, up=[0], down=[0], through=[1, 2, 3, 4]),
        NodeArt(at=4, up=[0, 4], down=[0], through=[1, 2, 3]),
        NodeArt(at=3, up=[0, 3], down=[0], through=[1, 2]),
        NodeArt(at=2, up=[0, 2], down=[0], through=[1]),
        NodeArt(at=1, up=[0, 1], down=[0]),
        NodeArt(at=1, up=[0], down=[0]),
        NodeArt(at=0, up=[0]),
        NodeArt(at=0),
    ]
    output = "".join(str(row) + "\n" for row in grid)
    assert output == dedent(
        """\
      ┬
      ┼
      ┼
      ┼
      ┼
      ┼
      ┼◀┬─┬─┐
      ┼◀│┄│┄│┄┐
      ┼ │ │ │ │
      ├┄│┄│┄│▶┘
      ├┄│┄│▶┘
      ├┄│▶┘
      ├▶┘
      ├▶╴
      ┴
      ─
  """
    )


def test_row_unicode_remerge_to_head() -> None:
    grid = [
        NodeArt(at=1, down=[1]),
        NodeArt(at=0, up=[1], down=[0, 1]),
        NodeArt(at=0, up=[0], down=[0], through=[1]),
        NodeArt(at=1, up=[0, 1], down=[0]),
        NodeArt(at=0, up=[0]),
    ]
    output = "".join(str(row) + "\n" for row in grid)
    assert output == dedent(
        """\
        ┬
      ┬◀┤
      ┼ │
      ├▶┘
      ┴
  """
    )


def test_row_unicode_simple_merge_to_head_with_crossunder() -> None:
    grid = [
        NodeArt(at=0, down=[0, 1]),
        NodeArt(at=2, up=[0], down=[0], through=[1]),
        NodeArt(at=0, up=[0], down=[0], through=[1]),
        NodeArt(at=1, up=[0, 1], down=[0]),
        NodeArt(at=0, up=[0]),
    ]
    output = "".join(str(row) + "\n" for row in grid)
    assert output == dedent(
        """\
      ┬◀┐
      ├┄│▶╴
      ┼ │
      ├▶┘
      ┴
  """
    )


def test_row_unicode_remerge_head_into_branch() -> None:
    grid = [
        NodeArt(at=0, down=[0]),
        NodeArt(at=1, down=[1], through=[0]),
        NodeArt(at=1, up=[0, 1], down=[0, 1]),
        NodeArt(at=0, up=[0], down=[0], through=[1]),
        NodeArt(at=1, up=[0, 1], down=[0]),
        NodeArt(at=0, up=[0]),
    ]
    output = "".join(str(row) + "\n" for row in grid)
    assert output == dedent(
        """\
      ┬
      │ ┬
      ├▶┼
      ┼ │
      ├▶┘
      ┴
  """
    )
