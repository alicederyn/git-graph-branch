from typing import Iterator, cast
from unittest.mock import Mock

from git_graph_branch.dag import DAG
from git_graph_branch.git.branch import Branch
from git_graph_branch.git.branch_algos import compute_branch_dag
from git_graph_branch.git.commit import Commit
from git_graph_branch.git.reflog import ReflogEntry


def mock_commit(hash: str, commit_date: int, *parents: Commit | None) -> Commit:
    commit = Mock(name=hash, spec=Commit)
    commit.commit_date = commit_date
    commit.hash = hash
    commit.first_parent = parents[0] if parents else None
    commit.available_parents.return_value = [p for p in parents if p is not None]
    commit.available_merge_parents.return_value = [
        p for p in parents[1:] if p is not None
    ]

    return commit


class MockBranch:
    def __init__(
        self,
        name: str,
        commit: Commit,
        upstream: Branch | None,
        reflog: list[Commit | tuple[Commit, int]],
    ) -> None:
        self._name = name
        self.commit = commit
        self.upstream = upstream
        self._reflog = reflog

    def __repr__(self) -> str:
        return self._name

    def reflog(self) -> Iterator[ReflogEntry]:
        for entry in self._reflog:
            if isinstance(entry, tuple):
                yield ReflogEntry(entry[0], entry[1])
            else:
                yield ReflogEntry(entry, entry.commit_date)


def mock_branch(
    name: str,
    commit: Commit,
    upstream: Branch | None = None,
    reflog: list[Commit | tuple[Commit, int]] | None = None,
) -> Branch:
    return cast(Branch, MockBranch(name, commit, upstream, reflog or [commit]))


def test_simple_chain_no_merges() -> None:
    # a -- b -- c -- d -- e
    # ↑         ↑         ↑
    # X         Y         Z
    a = mock_commit("a", 100)
    b = mock_commit("b", 300, a)
    c = mock_commit("c", 310, b)
    d = mock_commit("d", 320, c)
    e = mock_commit("e", 500, d)
    x = mock_branch("X", a)
    y = mock_branch("Y", c, x)
    z = mock_branch("Z", e, y)

    dag = compute_branch_dag([x, y, z])

    assert dag == DAG(edges=[(x, y), (y, z)])


def test_simple_merge() -> None:
    # X         Z
    # ↓         ↓
    # a -- b -- e
    #  \       /
    #   c --- d  ← Y
    a = mock_commit("a", 100)
    b = mock_commit("b", 300, a)
    c = mock_commit("c", 310, a)
    d = mock_commit("d", 320, c)
    e = mock_commit("e", 500, b, d)
    x = mock_branch("X", a)
    y = mock_branch("Y", d, x)
    z = mock_branch("Z", e, x)

    dag = compute_branch_dag([x, y, z])

    assert dag == DAG(edges=[(x, y), (x, z), (y, z)])


def test_past_merge() -> None:
    # X              Z
    # ↓              ↓
    # a -- b -- e -- f
    #  \       /
    #   c --- d  ← Y
    a = mock_commit("a", 100)
    b = mock_commit("b", 300, a)
    c = mock_commit("c", 310, a)
    d = mock_commit("d", 320, c)
    e = mock_commit("e", 500, b, d)
    f = mock_commit("f", 510, e)
    x = mock_branch("X", a)
    y = mock_branch("Y", d, x)
    z = mock_branch("Z", f, x)

    dag = compute_branch_dag([x, y, z])

    assert dag == DAG(edges=[(x, y), (x, z), (y, z)])


def test_cyclic_merge() -> None:
    # If there is a cyclic merge, the most recent
    # merge should take priority
    # X              Z
    # ↓              ↓
    # a -- b -- f -- g
    #  \    \       /
    #   c --- d -- e  ← Y
    a = mock_commit("a", 100)
    b = mock_commit("b", 300, a)
    c = mock_commit("c", 310, a)
    d = mock_commit("d", 320, c, b)
    e = mock_commit("e", 500, d)
    f = mock_commit("f", 510, b)
    g = mock_commit("g", 520, f, e)
    x = mock_branch("X", a)
    y = mock_branch("Y", e, x)
    z = mock_branch("Z", g, x)

    dag = compute_branch_dag([x, y, z])

    assert dag == DAG(edges=[(x, y), (x, z), (y, z)])


def test_altered_history() -> None:
    # X         Z
    # ↓         ↓
    # a -- b -- e
    # |\       /
    # | c --- d
    #  \
    #   c' -- d' ← Y
    #
    # Y used to refer to d
    a = mock_commit("a", 100)
    b = mock_commit("b", 300, a)
    c = mock_commit("c", 310, a)
    d = mock_commit("d", 320, c)
    e = mock_commit("e", 500, b, d)
    c_prime = mock_commit("c'", 600, a)
    d_prime = mock_commit("d'", 601, c_prime)
    x = mock_branch("X", a)
    y = mock_branch("Y", d_prime, x, reflog=[d_prime, d, c, (a, 305)])
    z = mock_branch("Z", e, x)

    dag = compute_branch_dag([x, y, z])

    assert dag == DAG(edges=[(x, y), (x, z), (y, z)])


def test_overlapping_reflogs() -> None:
    # W         Z
    # ↓         ↓
    # a -- b -- e
    #  \       /
    #   c --- d -- f  ← Y
    #    \
    #     d'  ← X
    #
    # Both X and Y used to refer to d, but X referred to it first
    a = mock_commit("a", 100)
    b = mock_commit("b", 300, a)
    c = mock_commit("c", 310, a)
    d = mock_commit("d", 320, c)
    e = mock_commit("e", 400, b, d)
    f = mock_commit("f", 500, d)
    d_prime = mock_commit("d'", 800, c)
    w = mock_branch("W", a)
    x = mock_branch("X", d_prime, w, reflog=[d_prime, d, c, a])
    y = mock_branch("Y", f, w, reflog=[f, (d, 480)])
    z = mock_branch("Z", e, w)

    dag = compute_branch_dag([w, x, y, z])

    assert dag == DAG(edges=[(w, x), (w, y), (w, z), (x, z)])
