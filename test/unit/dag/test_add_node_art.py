# coding=utf-8
from __future__ import annotations

from dataclasses import dataclass

from git_graph_branch.dag import NodeArt, add_node_art, inverted


@dataclass(frozen=True)
class Node:
    identifier: int


def test_add_node_art_multi_branch_merge() -> None:
    branches = [Node(n) for n in range(16)]
    parents: dict[Node, set[Node]] = {
        branches[15]: set(),
        branches[14]: set(),
        branches[13]: {branches[14]},
        branches[12]: {branches[14]},
        branches[11]: {branches[14]},
        branches[10]: {branches[14]},
        branches[9]: {branches[14]},
        branches[8]: {branches[14]},
        branches[7]: {branches[9], branches[8]},
        branches[6]: {branches[12], branches[11], branches[10], branches[7]},
        branches[5]: {branches[6]},
        branches[4]: {branches[5]},
        branches[3]: {branches[4]},
        branches[2]: {branches[3]},
        branches[1]: {branches[2]},
        branches[0]: {branches[1]},
    }
    children = inverted(parents)

    node_art = add_node_art(branches, parents, children)

    assert node_art == [
        (NodeArt(at=0, down=[0]), branches[0]),
        (NodeArt(at=0, up=[0], down=[0]), branches[1]),
        (NodeArt(at=0, up=[0], down=[0]), branches[2]),
        (NodeArt(at=0, up=[0], down=[0]), branches[3]),
        (NodeArt(at=0, up=[0], down=[0]), branches[4]),
        (NodeArt(at=0, up=[0], down=[0]), branches[5]),
        (NodeArt(at=0, up=[0], down=[0, 1, 2, 3]), branches[6]),
        (NodeArt(at=0, up=[0], down=[0, 4], through=[1, 2, 3]), branches[7]),
        (NodeArt(at=0, up=[0], down=[0], through=[1, 2, 3, 4]), branches[8]),
        (NodeArt(at=4, up=[0, 4], down=[0], through=[1, 2, 3]), branches[9]),
        (NodeArt(at=3, up=[0, 3], down=[0], through=[1, 2]), branches[10]),
        (NodeArt(at=2, up=[0, 2], down=[0], through=[1]), branches[11]),
        (NodeArt(at=1, up=[0, 1], down=[0]), branches[12]),
        (NodeArt(at=1, up=[0], down=[0]), branches[13]),
        (NodeArt(at=0, up=[0]), branches[14]),
        (NodeArt(at=0), branches[15]),
    ]


def test_add_node_art_simple_merge_with_crossover() -> None:
    branches = [Node(n) for n in range(5)]
    parents: dict[Node, set[Node]] = {
        branches[4]: set(),
        branches[3]: {branches[4]},
        branches[2]: {branches[4]},
        branches[1]: {branches[3], branches[2]},
        branches[0]: {branches[3]},
    }
    children = inverted(parents)

    node_art = add_node_art(branches, parents, children)

    assert node_art == [
        (NodeArt(at=1, down=[1]), branches[0]),
        (NodeArt(at=0, up=[1], down=[0, 1]), branches[1]),
        (NodeArt(at=0, up=[0], down=[0], through=[1]), branches[2]),
        (NodeArt(at=1, up=[0, 1], down=[0]), branches[3]),
        (NodeArt(at=0, up=[0]), branches[4]),
    ]


def test_add_node_art_simple_merge_no_crossover() -> None:
    branches = [Node(n) for n in range(5)]
    parents: dict[Node, set[Node]] = {
        branches[4]: set(),
        branches[3]: {branches[4]},
        branches[2]: {branches[4]},
        branches[1]: {branches[2]},
        branches[0]: {branches[2], branches[3]},
    }
    children = inverted(parents)

    node_art = add_node_art(branches, parents, children)

    assert node_art == [
        (NodeArt(at=0, down=[0, 1]), branches[0]),
        (NodeArt(at=2, up=[0], down=[0], through=[1]), branches[1]),
        (NodeArt(at=0, up=[0], down=[0], through=[1]), branches[2]),
        (NodeArt(at=1, up=[0, 1], down=[0]), branches[3]),
        (NodeArt(at=0, up=[0]), branches[4]),
    ]
