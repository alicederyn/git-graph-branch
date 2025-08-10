from itertools import permutations
from unittest.mock import Mock, PropertyMock

from git_graph_branch.git.commit import Commit, MissingCommit
from git_graph_branch.git.commit_algos import common_ancestor

next_hash = 0


def mock_commit(
    *, commit_date: int = 0, hash: str | None = None, parent: Commit | None = None
) -> Commit:
    commit = Mock(spec=Commit)
    commit.commit_date = commit_date
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
    type(commit).commit_date = PropertyMock(side_effect=MissingCommit)
    type(commit).first_parent = PropertyMock(side_effect=MissingCommit)
    return commit


def test_simple_child_branch() -> None:
    a = mock_commit(commit_date=100)
    b = mock_commit(commit_date=200, parent=a)
    c = mock_commit(commit_date=210, parent=b)
    d = mock_commit(commit_date=240, parent=c)

    assert common_ancestor(b, d) == b
    assert common_ancestor(d, b) == b


def test_three_branches() -> None:
    a = mock_commit(commit_date=100)
    b = mock_commit(commit_date=200, parent=a)
    c = mock_commit(commit_date=210, parent=b)
    d = mock_commit(commit_date=240, parent=c)
    e = mock_commit(commit_date=250, parent=b)
    f = mock_commit(commit_date=300, parent=c)

    for x, y, z in permutations([d, e, f], 3):
        assert common_ancestor(x, y, z) == b


def test_early_clock_skew() -> None:
    a = mock_commit(commit_date=10)
    b = mock_commit(commit_date=100, parent=a)
    c = mock_commit(commit_date=90, parent=b)
    d = mock_commit(commit_date=110, parent=b)

    assert common_ancestor(c, d) == b
    assert common_ancestor(d, c) == b
