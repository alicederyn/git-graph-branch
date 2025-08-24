from typing import Iterator, cast
from unittest.mock import Mock

from git_graph_branch.git.commit import Commit, MissingCommit
from git_graph_branch.git.commit_algos import range


class FakeMissingCommit:
    """A fake commit that is missing data due to shallow cloning."""

    def __init__(self, commit_date: int, hash: str):
        self.commit_date = commit_date
        self.hash = hash

    @property
    def first_parent(self) -> Commit | None:
        raise MissingCommit(self.hash)

    def available_parents(self) -> Iterator[Commit]:
        return iter([])


def missing_commit(*, commit_date: int, hash: str) -> Commit:
    return cast(Commit, FakeMissingCommit(commit_date, hash))


def mock_commit(
    *, commit_date: int = 0, hash: str, parents: tuple[Commit, ...] = ()
) -> Commit:
    commit = Mock(
        name=f"Commit({hash})",
        spec=Commit,
        commit_date=commit_date,
        hash=hash,
        first_parent=parents[0] if parents else None,
    )
    commit.available_parents.return_value = parents
    return commit


def test_linear_history() -> None:
    # a  <-- upstream
    #  \
    #   b
    #    \
    #     c  <-- downstream
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b")
    c = mock_commit(commit_date=300, hash="c", parents=(b,))

    # Should return all commits since there's no common history
    result = list(range(upstream=a, downstream=c))
    assert result == [c, b]


def test_same_commit() -> None:
    a = mock_commit(commit_date=100, hash="a")
    result = list(range(upstream=a, downstream=a))
    assert result == []


def test_merge_commit() -> None:
    # a -- b -- c   <-- upstream
    #       \
    #        d -- e   <-- downstream
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b", parents=(a,))
    c = mock_commit(commit_date=300, hash="c", parents=(b,))
    d = mock_commit(commit_date=250, hash="d", parents=(b,))
    e = mock_commit(commit_date=350, hash="e", parents=(d,))

    # Should return e, d (in reverse order)
    result = list(range(upstream=c, downstream=e))
    assert result == [e, d]


def test_clock_drift() -> None:
    """Test with clock drift between branches."""
    # u4(100) -- u3(200) -- u2(300) -- u1(400) -- u0(500)   <-- upstream
    #              \
    #               d1(180) -- d2(220) -- d3(280) -- d4(380) -- d5(480)   <-- downstream
    u4 = mock_commit(commit_date=100, hash="u4")
    u3 = mock_commit(commit_date=200, hash="u3", parents=(u4,))
    u2 = mock_commit(commit_date=300, hash="u2", parents=(u3,))
    u1 = mock_commit(commit_date=400, hash="u1", parents=(u2,))
    u0 = mock_commit(commit_date=500, hash="u0", parents=(u1,))
    d1 = mock_commit(commit_date=180, hash="d1", parents=(u3,))
    d2 = mock_commit(commit_date=220, hash="d2", parents=(d1,))
    d3 = mock_commit(commit_date=280, hash="d3", parents=(d2,))
    d4 = mock_commit(commit_date=380, hash="d4", parents=(d3,))
    d5 = mock_commit(commit_date=480, hash="d5", parents=(d4,))

    # Should return all downstream commits until u3
    result = list(range(upstream=u0, downstream=d5, window_size_secs=50))
    assert result == [d5, d4, d3, d2, d1]


def test_shallow_clone() -> None:
    # Most history is unavailable due to the shallow clone
    # ? .. a   <-- upstream
    # ? .. b -- c   <-- downstream
    a = missing_commit(commit_date=300, hash="a")
    b = missing_commit(commit_date=250, hash="b")
    c = mock_commit(commit_date=350, hash="c", parents=(b,))

    # Should return c, b and stop when d raises MissingCommit
    result = list(range(upstream=a, downstream=c))
    assert result == [c, b]
