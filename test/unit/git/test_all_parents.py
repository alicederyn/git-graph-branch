from unittest.mock import Mock

from git_graph_branch.git.commit import Commit
from git_graph_branch.git.commit_algos import all_parents

next_hash = 0


def mock_commit(
    *, commit_date: int = 0, hash: str | None = None, parents: tuple["Commit", ...] = ()
) -> Commit:
    """Helper function to create a mock commit with the given properties."""
    global next_hash
    commit = Mock(spec=Commit)
    commit.commit_date = commit_date
    if hash is None:
        hash = f"{next_hash:040x}"
        next_hash += 1
    commit.hash = hash

    commit.parents = parents
    commit.first_parent = parents[0] if parents else None
    commit.available_parents.return_value = parents

    return commit


def test_single_commit() -> None:
    """Test with a single commit with no parents."""
    a = mock_commit(commit_date=100, hash="a")

    result = list(all_parents(a))

    commit_hashes = [commit.hash for commit in result]
    assert commit_hashes == ["a"]


def test_linear_history() -> None:
    """Test with a simple linear history."""
    # a <- b <- c
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b", parents=(a,))
    c = mock_commit(commit_date=300, hash="c", parents=(b,))

    result = list(all_parents(c))

    commit_hashes = [commit.hash for commit in result]
    assert commit_hashes == ["c", "b", "a"]


def test_merge_commit() -> None:
    """Test with a merge commit."""
    #   a
    #  / \
    # b   c
    #  \ /
    #   d
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b", parents=(a,))
    c = mock_commit(commit_date=150, hash="c", parents=(a,))
    d = mock_commit(commit_date=250, hash="d", parents=(b, c))

    result = list(all_parents(d))

    commit_hashes = [commit.hash for commit in result]
    assert commit_hashes == ["d", "b", "c", "a"]


def test_multiple_parents() -> None:
    """Test with a commit that has multiple parents."""
    #   a   b
    #    \ /
    #     c
    a = mock_commit(commit_date=100, hash="a")
    b = mock_commit(commit_date=200, hash="b")
    c = mock_commit(commit_date=300, hash="c", parents=(a, b))

    result = list(all_parents(c))

    commit_hashes = [commit.hash for commit in result]
    assert commit_hashes == ["c", "b", "a"]


def test_out_of_order_commit_dates() -> None:
    """Test handling of out-of-order commit_dates in a diamond merge.
    
    Simulates clock drift where child commits have slightly earlier commit_dates
    than their parent.
    
    Graph:
      a
     / \\
    b   c  (b and c have slightly earlier commit_dates than a due to clock drift)
    \\ /
     d
    """
    # Base commit
    a = mock_commit(commit_date=1000, hash="a")

    # Child commits with slightly earlier commit_dates (simulating clock drift)
    b = mock_commit(commit_date=999, hash="b", parents=(a,))
    c = mock_commit(commit_date=998, hash="c", parents=(a,))

    # Merge commit
    d = mock_commit(commit_date=1001, hash="d", parents=(b, c))

    # Get all commits in the graph
    result = list(all_parents(d))

    # All commits should be present exactly once
    # Order is no longer guaranteed
    sorted_hashes = sorted(commit.hash for commit in result)
    assert sorted_hashes == ["a", "b", "c", "d"]
