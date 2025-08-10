from unittest.mock import Mock

from git_graph_branch.git.commit import Commit
from git_graph_branch.git.commit_algos import last_merged_commit


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
    assert last_merged_commit(upstream=a, downstream=a) == a


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
    assert last_merged_commit(upstream=b, downstream=c) == b


def test_only_uses_first_parent_of_upstream() -> None:
    #  a ------- d   <-- upstream
    #   \       /
    #    b --- c   <-- downstream
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b", parents=(a,))
    c = mock_commit(commit_date=300, hash="c", parents=(b,))
    d = mock_commit(commit_date=400, hash="d", parents=(a, c))

    # c is reachable from d, but not by first parents only
    assert last_merged_commit(upstream=d, downstream=c) == a


def test_no_common_history() -> None:
    """Test when upstream and downstream have no common history."""
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b")

    assert last_merged_commit(upstream=a, downstream=b) is None


def test_clock_drift() -> None:
    """Upstream window extends across iterations with a small time window."""
    # Graph (commit_dates):
    # u4(100) -- u3(200) -- u2(300) -- u1(400) -- u0(500)   <-- upstream (first-parent only)
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

    # Ensure u3 is found despite the clock drift
    assert last_merged_commit(upstream=u0, downstream=d5, window_size_secs=50) == u3
