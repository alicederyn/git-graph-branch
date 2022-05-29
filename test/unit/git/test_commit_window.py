from typing import Iterable
from unittest.mock import Mock, PropertyMock

from git_graph_branch.git.commit import Commit, MissingCommit
from git_graph_branch.git.commit_algos import CommitWindow

next_hash = 0


def mock_commit(*, timestamp: int = 0, hash: str | None = None) -> Commit:
    commit = Mock(spec=Commit)
    commit.timestamp = timestamp
    if hash is None:
        global next_hash
        hash = "{0:40x}".format(next_hash)
        next_hash += 1
    commit.hash = hash
    return commit


def missing_commit(*, hash: str | None = None) -> Commit:
    commit = Mock(spec=Commit)
    commit.hash = hash
    type(commit).timestamp = PropertyMock(side_effect=MissingCommit)
    type(commit).first_parent = PropertyMock(side_effect=MissingCommit)
    return commit


def in_window(w: CommitWindow, commits: Iterable[Commit]) -> set[Commit]:
    return set(c for c in commits if c in w)


def test_membership_with_out_of_order_sequence() -> None:
    a = mock_commit(timestamp=100)
    b = mock_commit(timestamp=150)
    c = mock_commit(timestamp=145)
    d = mock_commit(timestamp=208)
    e = mock_commit(timestamp=400)
    f = mock_commit(timestamp=400)
    g = mock_commit(timestamp=600)
    commits = [a, b, c, d, e, f, g]

    w = CommitWindow(e)
    assert in_window(w, commits) == {e}
    w.add(d)
    assert in_window(w, commits) == {d, e}
    w.prune_to(d.timestamp)
    assert in_window(w, commits) == {d}
    w.add(c)
    assert in_window(w, commits) == {c, d}
    w.prune_to(c.timestamp)
    assert in_window(w, commits) == {c}
    w.add(b)
    assert in_window(w, commits) == {b, c}
    w.prune_to(b.timestamp)
    assert in_window(w, commits) == {b, c}
    w.add(a)
    assert in_window(w, commits) == {a, b, c}
    w.prune_to(a.timestamp)
    assert in_window(w, commits) == {a, b, c}
    w.add(None)
    assert in_window(w, commits) == {a, b, c}


def test_last_added_with_out_of_order_sequence() -> None:
    a = mock_commit(timestamp=150)
    b = mock_commit(timestamp=145)
    c = mock_commit(timestamp=208)

    w = CommitWindow(c)
    assert w.last_added == c
    w.add(b)
    assert w.last_added == b
    w.add(a)
    assert w.last_added == a
    w.add(None)
    assert w.last_added is None


def test_shallow_clone() -> None:
    """Test behaviour when commit is missing due to a shallow clone"""
    a = missing_commit()
    b = mock_commit(timestamp=150)
    c = mock_commit(timestamp=208)
    d = mock_commit(timestamp=300)
    commits = [d, c, b, a]

    w = CommitWindow(d)
    for commit in commits[1:]:
        w.add(commit)
    w.prune_to(b.timestamp)
    assert in_window(w, commits) == {a, b, c}
