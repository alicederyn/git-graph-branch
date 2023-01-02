from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from typing import Iterable

from hypothesis import given
from hypothesis import strategies as st

from git_graph_branch.dag import partially_ordered, reachable_from


@dataclass(frozen=True)
class Node:
    identifier: int


Edge = tuple[Node, Node]


class DAG:
    """Directed acyclic graphs."""

    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge] = ()) -> None:
        self.nodes = list(nodes)
        self.edges: list[Edge] = []
        self.parents: dict[Node, set[Node]] = {n: set() for n in self.nodes}
        self.children: dict[Node, set[Node]] = {n: set() for n in self.nodes}
        for edge in edges:
            self.add_edge(edge)

    def add_edge(self, edge: Edge) -> None:
        start, end = edge
        assert start in self.parents
        assert end in self.parents
        assert start not in self.parents[end]
        assert end not in self.children[start]
        self.edges.append(edge)
        self.children[start].add(end)
        self.parents[end].add(start)

    def connected_subgraph(self, node: Node) -> DAG:
        nodes = reachable_from(node, self.parents, self.children)
        nodes.add(node)
        return DAG(
            (n for n in self.nodes if n in nodes),
            (e for e in self.edges if e[0] in nodes),
        )

    def __repr__(self) -> str:
        return f"DAG(nodes={self.nodes}, edges={self.edges})"


def node_id(node: Node) -> int:
    return node.identifier


@st.composite
def nodes(draw: st.DrawFn) -> Node:
    return Node(identifier=draw(st.integers(min_value=0)))


@st.composite
def edges(draw: st.DrawFn, nodes: list[Node]) -> tuple[Node, Node]:
    assert len(nodes) >= 2
    start, end = sorted(
        draw(
            st.lists(
                st.integers(min_value=0, max_value=len(nodes) - 1),
                min_size=2,
                max_size=2,
                unique=True,
            )
        )
    )
    return nodes[start], nodes[end]


@st.composite
def dags(
    draw: st.DrawFn,
    *,
    min_nodes: int | None = None,
    max_nodes: int | None = None,
    min_edges: int = 0,
    max_edges: int | None = None,
) -> DAG:
    """Generates a random directed acyclic graph."""
    min_reqd_nodes = ceil(0.5 + sqrt(2 * min_edges - 0.25)) if min_edges else 0
    if min_nodes is None:
        min_nodes = min_reqd_nodes
    else:
        assert min_nodes >= min_reqd_nodes

    node_list = draw(
        st.lists(nodes(), min_size=min_nodes, max_size=max_nodes, unique=True)
    )

    N = len(node_list)
    max_poss_edges = N * (N - 1) // 2
    max_edges = (
        min(max_edges, max_poss_edges) if max_edges is not None else max_poss_edges
    )
    total_order = draw(st.permutations(node_list))
    edge_list = draw(
        st.lists(
            edges(total_order), min_size=min_edges, max_size=max_edges, unique=True
        )
    )

    graph = DAG(node_list)
    for edge in edge_list:
        graph.add_edge(edge)
    return graph


@given(graph=dags(min_edges=1))
def test_always_puts_child_first(graph: DAG) -> None:
    """Edges must always point up the list.

    Any implementation of partially_ordered MUST satisfy this constraint,
    as it is a requirement for NodeArt to function. For instance, in this
    trivial graph, the direction of the edge is not made explicit, and can
    be inferred from the ordering:

    ┬  feature
    ┴  main
    """
    # As the edges are in a random order, we can just check the first one
    node1, node2 = graph.edges[0]

    result = partially_ordered(graph.parents, graph.children, node_id)

    assert result.index(node1) > result.index(node2)


@given(graph=dags())
def test_puts_subgraphs_together(graph: DAG) -> None:
    """Disconnected subgraphs should not be interleaved.

    Any implementation of partially_ordered MUST satisfy this constraint,
    as otherwise the NodeArt becomes unnecessarily complex. For example:

    ┬  feature
    │ ─  gh-pages
    ┴  main

    Or even worse:

    ┬◀┄┄┐  feature 5
    ┼   │  feature 4
    │ ─ │  gh-pages
    │ ┬ │  feature 3
    │ ├▶┘  feature 2
    ├▶┘  feature 1
    ┴  main
    """
    result = partially_ordered(graph.parents, graph.children, node_id)

    connected: set[Node] = set()
    for node in result:
        if connected:
            assert node in connected
            connected.remove(node)
        else:
            connected = reachable_from(node, graph.parents, graph.children)


@given(graph=dags(min_nodes=2, max_edges=0))
def test_respects_ordering_when_no_edges(graph: DAG) -> None:
    """All else being equal, larger nodes will be placed first.

    In the absence of any other priorities, partially_ordered should fall
    back to the key ordering.
    """
    node1, node2 = sorted(graph.nodes[:2], key=node_id)

    result = partially_ordered(graph.parents, graph.children, node_id)

    assert result.index(node1) > result.index(node2)


@given(graph=dags())
def test_subgraphs_ordered_by_largest_node(graph: DAG) -> None:
    """partially_ordered should order subgraphs by key ordering.

    More specifically, each subgraph should be ordered using
    the largest key found within it."""
    result = partially_ordered(graph.parents, graph.children, node_id)

    idx = 0
    remaining = set(graph.nodes)
    while remaining:
        largest_remaining = max(remaining, key=node_id)
        subgraph = set(graph.connected_subgraph(largest_remaining).nodes)
        assert result[idx] in subgraph
        remaining -= subgraph
        idx += len(subgraph)


@given(graph=dags(min_nodes=1))
def test_largest_node_as_close_to_start_as_possible(graph: DAG) -> None:
    """partially_ordered should put the largest node as early as possible."""
    largest = max(graph.nodes, key=node_id)
    children = reachable_from(largest, graph.children)

    result = partially_ordered(graph.parents, graph.children, node_id)

    assert result.index(largest) == len(children)
