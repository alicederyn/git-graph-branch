# coding=utf-8
from __future__ import annotations

from collections import deque
from itertools import takewhile
from typing import (
    Any,
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Protocol,
    TypeVar,
    overload,
)


class HasLessThan(Protocol):
    def __lt__(self, __other: Any) -> bool:
        ...


class HasGreaterThan(Protocol):
    def __gt__(self, __other: Any) -> bool:
        ...


T = TypeVar("T")
C = TypeVar("C", bound=HasLessThan | HasGreaterThan)


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


def reachable_from(node: T, *relationships: Mapping[T, Collection[T]]) -> set[T]:
    all_reachable = {node}
    todo = [node]
    while todo:
        n = todo.pop()
        for relationship in relationships:
            for reachable_node in relationship[n]:
                if reachable_node not in all_reachable:
                    todo.append(reachable_node)
                    all_reachable.add(reachable_node)
    all_reachable.remove(node)
    return all_reachable


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


def lt(value: C) -> Callable[[C], bool]:
    try:
        return getattr(value, "__lt__")  # type: ignore
    except AttributeError:
        gt = getattr(value, "__gt__")

        def lt(k: Any) -> bool:
            return not gt(k)

        return lt


def priority_key(node_key: C, blocked_keys: Iterator[list[C]]) -> list[C]:
    """A "priority" key that inherits the priority of blocked nodes.

    For instance, in this case, a low-priority node is blocking two higher-
    priority nodes, so gets a key of slightly higher priority than both:
    >>> priority_key(1, [[2], [3]])
    [3, 1]
    """
    blocked_key: list[C] = max(blocked_keys, default=[])
    return [*takewhile(lt(node_key), blocked_key), node_key]


@overload
def partially_ordered(
    parents: Mapping[T, Collection[T]],
    children: Mapping[T, Collection[T]],
    key: Callable[[T], C],
) -> list[T]:
    ...


@overload
def partially_ordered(
    parents: Mapping[C, Collection[C]],
    children: Mapping[C, Collection[C]],
    key: None = ...,
) -> list[C]:
    ...


def partially_ordered(
    parents: Mapping[T, Collection[T]],
    children: Mapping[T, Collection[T]],
    key: Callable[[T], C] | None = None,
) -> list[T]:
    """Partially order nodes so children always precede parents.

    Larger nodes (according to < on the nodes, or their key if a key function is
    given) will be preferentially placed first, all other things being equal.
    """
    keys: dict[T, C] = {node: key(node) if key else node for node in parents}
    priority_keys: dict[T, tuple[C, list[C]]] = {}
    remaining = set(parents)

    while remaining:
        some_node = next(iter(remaining))
        todo = deque(reachable_from(some_node, parents, children))
        todo.append(some_node)
        cluster_key = max(keys[node] for node in todo)
        seen = set()  # Loop detection

        while todo:
            node = todo.pop()
            if node not in remaining:
                continue
            missing = [p for p in parents[node] if p in remaining]
            if missing and node not in seen:
                seen.add(node)
                todo.append(node)
                todo.extend(missing)
            else:
                # If node in seen, we have a loop; fail gracefully
                pkey: list[C] = priority_key(
                    keys[node],
                    (priority_keys[p][1] for p in parents[node] if p in priority_keys),
                )
                priority_keys[node] = (cluster_key, pkey)
                remaining.remove(node)

    return sorted(priority_keys, key=priority_keys.__getitem__, reverse=True)
