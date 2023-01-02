# coding=utf-8
from __future__ import annotations

from typing import Any, Collection, Iterable, Mapping, TypeVar

T = TypeVar("T")


class NodeArt:
    """Unicode art for a node in a DAG.

    Each node will be displayed in a separate row, and will be represented in
    the art by a single column in that row. All outgoing edges from that node
    will go straight up in that column to their target node's row. All
    incoming edges will have a right-angle in this row before joining the
    node; an arrow will be used just to the left/right of the node column
    to indicate directionality. Each edge column is separated by an extra
    column to allow room for "fade out" dashes (when two edges must cross)
    and directionality arrows.

    A node with no edges:
    >>> str(NodeArt(at=0))
    '─'

    A node with an outgoing edge:
    >>> str(NodeArt(at=0, up={0}))
    '┴'

    A node with an incoming edge:
    >>> str(NodeArt(at=0, down={0}))
    '┬'

    A node with two incoming edges:
    >>> str(NodeArt(at=0, down={0,1}))
    '┬◀┐'

    A node with an incoming and outgoing edge:
    >>> str(NodeArt(at=0, up={0}, down={0}))
    '┼'

    A node with an incoming and outgoing edge; another edge continues up from
    the same parent node:
    >>> str(NodeArt(at=1, up={0,1}, down={0}))
    '├▶┘'

    A node with three incoming and one outgoing edges; two edges pass without
    connecting.
    >>> str(NodeArt(3, up={3}, down={0, 2, 3}, through={1, 4}))
    '┌┄│┄┬▶┼ │'

    str(self): Unicode-art representation of this row, e.g. ├▶┘

    self.at: the "owner" column of the node
    self.up: columns with up edges the node is connected to
    self.down: columns with down edges the node is connected to
    self.through: columns this node is not connected to that still need an edge
    """

    BOX_CHARS = [
        " ",
        "╵",
        "╶",
        "└",
        "╷",
        "│",
        "┌",
        "├",
        "╴",
        "┘",
        "─",
        "┴",
        "┐",
        "┤",
        "┬",
        "┼",
    ]

    def __init__(
        self,
        at: int,
        up: Iterable[int] = (),
        down: Iterable[int] = (),
        through: Iterable[int] = (),
    ):
        self.at = at
        self.up = frozenset(up)
        self.down = frozenset(down)
        self.through = frozenset(through)
        self._min = min({self.at} | self.up | self.down)
        self._max = max({self.at} | self.up | self.down)
        self._cols = max({self._max} | self.through) + 1
        assert 0 <= self.at
        assert all(idx >= 0 for idx in self.up)
        assert all(idx >= 0 for idx in self.down)
        assert all(idx >= 0 for idx in self.through)
        assert not any(idx in self.up or idx in self.down for idx in self.through)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, NodeArt):
            return NotImplemented
        return (
            self.at == other.at
            and self.up == other.up
            and self.down == other.down
            and self.through == other.through
        )

    def __repr__(self) -> str:
        r = "%s(at = %d" % (type(self).__name__, self.at)
        if self.up:
            r += ", up = {%s}" % ",".join(map(str, sorted(self.up)))
        if self.down:
            r += ", down = {%s}" % ",".join(map(str, sorted(self.down)))
        if self.through:
            r += ", through = {%s}" % ",".join(map(str, sorted(self.through)))
        r += ")"
        return r

    def _first_codepoint(self, column: int) -> str:
        if column in self.through:
            up = down = True
            left = right = False
        else:
            up = column in self.up
            down = column in self.down
            if self._min == column == self._max:
                left = right = True
            elif self.at == column and column in self.down:
                left = right = True
            else:
                left = self._min < column <= self._max
                right = self._min <= column < self._max
        return NodeArt.BOX_CHARS[
            (1 if up else 0)
            + (2 if right else 0)
            + (4 if down else 0)
            + (8 if left else 0)
        ]

    def _second_codepoint(self, column: int) -> str:
        if column < self._cols - 1:
            if self._min <= column < self._max:
                if column + 1 == self.at:
                    return "▶"
                elif column == self.at:
                    return "◀"
                elif column in self.through or column + 1 in self.through:
                    return "┄"
                else:
                    return "─"
            else:
                return " "
        else:
            return ""

    def __str__(self) -> str:
        return "".join(
            self._first_codepoint(i) + self._second_codepoint(i)
            for i in range(self._cols)
        )


def inverted(relationship: Mapping[T, set[T]]) -> Mapping[T, set[T]]:
    inverse: dict[T, set[T]] = {b: set() for b in relationship}
    for key, values in relationship.items():
        for value in values:
            inverse[value].add(key)
    return inverse


def add_node_art(
    nodes: list[T], parents: Mapping[T, Collection[T]], children: Mapping[T, set[T]]
) -> list[tuple[NodeArt, T]]:
    """Add node art to a list of nodes to depict the associated edges.

    The node list must be partially ordered to respect the DAG. Specifically,
    edges must point up the list (or, equivalently, parents must come after
    children).
    """
    columns: dict[T, int] = {}
    active: list[T | None] = []
    reached: set[T] = set()
    grid: list[tuple[NodeArt, T]] = []
    for b in reversed(nodes):
        reached.add(b)

        finished_parents = [p for p in parents[b] if children[p] <= reached]
        at = (
            min(columns[p] for p in finished_parents)
            if finished_parents
            else len(active)
        )
        columns[b] = at
        down = {columns[p] for p in parents[b]}
        for p in parents[b]:
            if all(c in columns for c in children[p]):
                active[columns[p]] = None
        through = {
            idx for idx, p in enumerate(active) if p and idx != at and idx not in down
        }
        if children[b]:
            while len(active) <= at:
                active.append(None)
            active[at] = b
        up = {idx for idx, p in enumerate(active) if p and idx not in through}
        while active and active[-1] is None:
            active.pop()
        grid.append((NodeArt(at, up=up, down=down, through=through), b))
    grid.reverse()
    return grid
