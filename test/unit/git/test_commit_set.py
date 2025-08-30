from typing import Iterable
from unittest.mock import Mock, PropertyMock

import pytest

from git_graph_branch.git.commit import Commit, MissingCommit
from git_graph_branch.git.commit_algos import CommitSet

next_hash = 0


def mock_commit(*, commit_date: int = 0, hash: str | None = None) -> Commit:
    commit = Mock(spec=Commit)
    commit.commit_date = commit_date
    if hash is None:
        global next_hash
        hash = "{0:40x}".format(next_hash)
        next_hash += 1
    commit.hash = hash
    return commit


def missing_commit(*, hash: str | None = None) -> Commit:
    commit = Mock(spec=Commit)
    commit.hash = hash
    type(commit).commit_date = PropertyMock(side_effect=MissingCommit)
    type(commit).first_parent = PropertyMock(side_effect=MissingCommit)
    return commit


def in_window(w: CommitSet, commits: Iterable[Commit]) -> set[Commit]:
    return set(c for c in commits if c in w)


def test_membership_with_out_of_order_sequence() -> None:
    a = mock_commit(commit_date=100)
    b = mock_commit(commit_date=150)
    c = mock_commit(commit_date=145)
    d = mock_commit(commit_date=208)
    e = mock_commit(commit_date=400)
    f = mock_commit(commit_date=400)
    g = mock_commit(commit_date=600)
    commits = [a, b, c, d, e, f, g]

    w = CommitSet(e)
    assert in_window(w, commits) == {e}
    w.add(d)
    assert in_window(w, commits) == {d, e}
    w.remove_newer_than(d.commit_date + 60)
    assert in_window(w, commits) == {d}
    w.add(c)
    assert in_window(w, commits) == {c, d}
    w.remove_newer_than(c.commit_date + 60)
    assert in_window(w, commits) == {c}
    w.add(b)
    assert in_window(w, commits) == {b, c}
    w.remove_newer_than(b.commit_date + 60)
    assert in_window(w, commits) == {b, c}
    w.add(a)
    assert in_window(w, commits) == {a, b, c}
    w.remove_newer_than(a.commit_date + 60)
    assert in_window(w, commits) == {a, b, c}
    w.add(None)
    assert in_window(w, commits) == {a, b, c}


def test_last_added_with_out_of_order_sequence() -> None:
    a = mock_commit(commit_date=150)
    b = mock_commit(commit_date=145)
    c = mock_commit(commit_date=208)

    w = CommitSet(c)
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
    b = mock_commit(commit_date=150)
    c = mock_commit(commit_date=208)
    d = mock_commit(commit_date=300)
    commits = [d, c, b, a]

    w = CommitSet(d)
    for commit in commits[1:]:
        w.add(commit)
    w.remove_newer_than(b.commit_date + 60)
    assert in_window(w, commits) == {a, b, c}


def test_pop() -> None:
    c1 = mock_commit(commit_date=100)
    c2 = mock_commit(commit_date=101)
    c3 = mock_commit(commit_date=102)
    c4 = mock_commit(commit_date=103)

    w = CommitSet(c3)
    w.add(c1)
    w.add(c2)
    w.add(c4)
    w.add(c3)

    assert w.pop() == c4
    assert w.pop() == c3
    assert w.pop() == c2
    assert w.pop() == c1

    with pytest.raises(KeyError):
        w.pop()

    assert c4 not in w


def test_remove() -> None:
    c1 = mock_commit(commit_date=100)
    c2 = mock_commit(commit_date=101)

    w = CommitSet(c1)
    w.add(c2)
    w.remove(c2)

    assert c2 not in w
    assert w.pop() == c1
