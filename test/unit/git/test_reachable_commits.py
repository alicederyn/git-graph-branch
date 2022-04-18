from typing import Iterable
from unittest.mock import Mock, PropertyMock

from git_graph_branch.git.commit import Commit, MissingCommit
from git_graph_branch.git.commit_containers import ReachableCommits

next_hash = 0


def mock_commit(
    *, timestamp: int = 0, hash: str | None = None, parent: Commit | None = None
) -> Commit:
    commit = Mock(spec=Commit)
    commit.timestamp = timestamp
    if hash is None:
        global next_hash
        hash = "{0:40x}".format(next_hash)
        next_hash += 1
    commit.hash = hash
    commit.first_parent = parent
    return commit


def missing_commit(*, hash: str | None = None) -> Commit:
    commit = Mock(spec=Commit)
    commit.hash = hash
    type(commit).timestamp = PropertyMock(side_effect=MissingCommit)
    type(commit).first_parent = PropertyMock(side_effect=MissingCommit)
    return commit


def filter(reachable: ReachableCommits, commits: Iterable[Commit]) -> set[Commit]:
    return {c for c in commits if c in reachable}


def test_edge_cases() -> None:
    """Test various awkward edge cases

    A - B - C - D  # C is timestamped a few seconds before B
    |
    E - F - G
        |
        H
    """
    a = mock_commit(timestamp=100)
    b = mock_commit(timestamp=150, parent=a)
    c = mock_commit(timestamp=145, parent=b)
    d = mock_commit(timestamp=208, parent=c)
    e = mock_commit(timestamp=400, parent=a)
    f = mock_commit(timestamp=600, parent=e)
    g = mock_commit(timestamp=750, parent=f)
    h = mock_commit(timestamp=800, parent=f)
    k = mock_commit(timestamp=900, parent=h)
    m = mock_commit(timestamp=410, parent=c)
    expected_reachable = {a, b, c, d, e, f, g, h}
    reachable = ReachableCommits([d, h, g])

    for commit in [k, h, f, m, d, c, b, a]:
        reachable.rewind_to(commit)
        if commit in expected_reachable:
            assert commit in reachable
        else:
            assert commit not in reachable


def test_shallow_clone() -> None:
    """Test behaviour when some commits are missing due to a shallow clone"""
    c = missing_commit()
    d = mock_commit(timestamp=208, parent=c)
    e = missing_commit()
    f = mock_commit(timestamp=600, parent=e)
    g = mock_commit(timestamp=750, parent=f)
    h = mock_commit(timestamp=800, parent=f)
    k = mock_commit(timestamp=900, parent=h)
    m = mock_commit(timestamp=410, parent=c)
    expected_reachable = {d, f, g, h}
    reachable = ReachableCommits([d, h, g])

    for commit in [k, h, f, m, d]:
        reachable.rewind_to(commit)
        if commit in expected_reachable:
            assert commit in reachable
        else:
            assert commit not in reachable

    # Do not explode if rewound to a missing commit
    reachable.rewind_to(e)
