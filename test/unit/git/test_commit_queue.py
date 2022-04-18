from unittest.mock import Mock

from git_graph_branch.git.commit import Commit
from git_graph_branch.git.commit_containers import CommitQueue

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


def test_peek_empty_queue() -> None:
    q = CommitQueue()
    assert q.peek() is None


def test_pop_empty_queue() -> None:
    q = CommitQueue()
    assert q.pop() is None


def test_push_single_element() -> None:
    commit = mock_commit()
    q = CommitQueue()
    q.push(commit)
    assert q.peek() is commit
    assert q.pop() is commit
    assert q.peek() is None
    assert q.pop() is None


def test_push_two_elements_earlier_first() -> None:
    commit1 = mock_commit(timestamp=12345)
    commit2 = mock_commit(timestamp=21347)  # later timestamp than commit1
    q = CommitQueue()
    q.push(commit1)
    q.push(commit2)
    assert q.peek() is commit2
    assert q.pop() is commit2
    assert q.peek() is commit1
    assert q.pop() is commit1
    assert q.peek() is None
    assert q.pop() is None


def test_push_two_elements_later_first() -> None:
    commit1 = mock_commit(timestamp=12345)
    commit2 = mock_commit(timestamp=21347)  # later timestamp than commit1
    q = CommitQueue()
    q.push(commit2)
    q.push(commit1)
    assert q.peek() is commit2
    assert q.pop() is commit2
    assert q.peek() is commit1
    assert q.pop() is commit1
    assert q.peek() is None
    assert q.pop() is None


def test_push_deduplicates_head() -> None:
    commit = mock_commit()
    q = CommitQueue()
    for _ in range(10):
        q.push(commit)
    assert len(q) == 1


def test_pop_deduplicates() -> None:
    # Deduplicating if a commit is not at the head of the queue would
    # be fairly expensive; instead, deduplication will be done at pop
    commit1 = mock_commit(timestamp=12345)
    commit2 = mock_commit(timestamp=21347)  # later timestamp than commit1
    q = CommitQueue()
    q.push(commit2)
    for _ in range(10):
        q.push(commit1)
    assert len(q) == 11
    assert q.pop() == commit2
    assert len(q) == 10
    assert q.pop() == commit1
    assert len(q) == 0
    assert q.pop() is None
