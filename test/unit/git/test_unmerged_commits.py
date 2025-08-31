from unittest.mock import Mock

from git_graph_branch.git.commit import Commit
from git_graph_branch.git.commit_algos import unmerged_commits


def mock_commit(
    *, commit_date: int = 0, hash: str, parents: tuple[Commit, ...] = ()
) -> Commit:
    """Helper function to create a mock commit with the given properties."""
    commit = Mock(name=f"Commit({hash})", spec=Commit)
    commit.commit_date = commit_date
    commit.hash = hash
    commit.first_parent = parents[0] if parents else None
    commit.available_parents.return_value = parents

    return commit


def test_same_commit() -> None:
    """Test when upstream and downstream are the same commit."""
    a = mock_commit(commit_date=100, hash="a")
    assert list(unmerged_commits(upstream=a, downstream=a)) == []


def test_merge_commit() -> None:
    """Test with a merge commit."""
    # Create a simple merge scenario:
    #   a   b  <-- upstream
    #    \ /
    #     c  <-- downstream
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b")
    c = mock_commit(commit_date=300, hash="c", parents=(a, b))

    # The most recent commit in feature branch that's in the merge commit is 'b'
    assert list(unmerged_commits(upstream=b, downstream=c)) == []


def test_only_uses_first_parent_of_upstream() -> None:
    #  a ------- d   <-- upstream
    #   \       /
    #    b --- c   <-- downstream
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b", parents=(a,))
    c = mock_commit(commit_date=300, hash="c", parents=(b,))
    d = mock_commit(commit_date=400, hash="d", parents=(a, c))

    # c is reachable from d, but not by first parents only
    assert list(unmerged_commits(upstream=d, downstream=c)) == [d]


def test_no_common_history() -> None:
    """Test when upstream and downstream have no common history."""
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b")

    assert list(unmerged_commits(upstream=a, downstream=b)) == [a]


def test_clock_drift() -> None:
    """Upstream window extends across iterations with a small time window."""
    # Graph (commit_dates):
    # u1 (101) -- u2 (100) <-- upstream
    #   \           \
    #    d1 (102) -- d2 (103) <-- downstream
    u1 = mock_commit(commit_date=101, hash="u1")
    d1 = mock_commit(commit_date=101, hash="d1", parents=(u1,))
    u2 = mock_commit(commit_date=100, hash="u2", parents=(u1,))
    d2 = mock_commit(commit_date=103, hash="d2", parents=(d1, u2))

    assert list(unmerged_commits(upstream=u2, downstream=d2, window_size_secs=50)) == []
