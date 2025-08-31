from collections.abc import MutableSet
from functools import total_ordering
from heapq import heappop, heappush
from typing import Any, Callable, Iterator

from .commit import Commit, MissingCommit


@total_ordering
class ChronoCommit:
    """Orders commits based on their commit_date

    More recent commits are higher priority (i.e. smaller)
    """

    def __init__(self, commit: Commit):
        self.commit = commit
        try:
            self._key = (-commit.commit_date, commit.hash)
        except MissingCommit:
            self._key = (1, commit.hash)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ChronoCommit):
            return False
        return self.commit == other.commit

    def __lt__(self, other: "ChronoCommit") -> bool:
        return self._key < other._key

    def is_newer_than(self, commit_date: int) -> bool:
        return -self._key[0] > commit_date


class CommitHeap[V]:
    """Stores a heap of commits, with O(1) access to the newest commit."""

    def __init__(
        self, still_contains: Callable[[Commit], bool], on_remove: Callable[[Commit], V]
    ):
        self._heap: list[ChronoCommit] = []
        self.still_contains = still_contains
        self.on_remove = on_remove

    def add(self, commit: Commit) -> None:
        heappush(self._heap, ChronoCommit(commit))

    def remove_newer_than(self, commit_date: int) -> None:
        while self._heap and self._heap[0].is_newer_than(commit_date):
            commit = heappop(self._heap).commit
            try:
                self.on_remove(commit)
            except KeyError:
                pass

    def peek(self) -> Commit | None:
        while self._heap and (commit := self._heap[0].commit) is not None:
            if self.still_contains(commit):
                return commit
            heappop(self._heap)
        return None

    def pop(self) -> tuple[Commit, V]:
        while True:
            try:
                commit = heappop(self._heap).commit
            except IndexError:
                raise KeyError() from None
            try:
                value = self.on_remove(commit)
                return (commit, value)
            except KeyError:
                pass


class CommitSet(MutableSet[Commit]):
    """Stores a set of commits, with O(1) access to the newest commit."""

    def __init__(self, *commits: Commit):
        self._commits = set(commits)
        self._heap = CommitHeap(
            still_contains=lambda x: x in self._commits, on_remove=self._commits.remove
        )
        for commit in commits:
            self._heap.add(commit)
        self.last_added = commits[-1] if commits else None

    def __contains__(self, commit: object, /) -> bool:
        return commit in self._commits

    def __iter__(self) -> Iterator[Commit]:
        return iter(self._commits)

    def __len__(self) -> int:
        return len(self._commits)

    def add(self, commit: Commit | None) -> None:
        """Add a commit to the window."""
        self.last_added = commit
        if commit:
            self._commits.add(commit)
            self._heap.add(commit)

    def discard(self, value: Commit) -> None:
        self._commits.discard(value)

    def has_commit_newer_than(self, timestamp: int) -> bool:
        commit = self._heap.peek()
        return commit is not None and commit.commit_date > timestamp

    def peek(self) -> Commit:
        commit = self._heap.peek()
        if not commit:
            raise KeyError()
        return commit

    def pop(self) -> Commit:
        return self._heap.pop()[0]

    def remove_newer_than(self, commit_date: int) -> None:
        """Prune all commits newer than commit_date."""
        self._heap.remove_newer_than(commit_date)


class WindowedReachable:
    def __init__(self, commit: Commit, *, window_size_secs: int = 60) -> None:
        self._reachable = CommitSet(commit)
        self._todo = CommitSet(commit)
        self.window_size_secs = window_size_secs

    def _slide_window_to(self, ts: int) -> None:
        window_top = ts + self.window_size_secs
        self._reachable.remove_newer_than(ts + self.window_size_secs)
        while self._todo and self._todo.peek().commit_date >= ts - self.window_size_secs:
            commit = self._todo.pop()
            for parent in commit.available_parents():
                self._todo.add(parent)
                if parent.commit_date <= window_top:
                    self._reachable.add(parent)

    def __contains__(self, commit: Commit) -> bool:
        self._slide_window_to(commit.commit_date)
        return commit in self._reachable


def last_merged_commit(
    upstream: Commit, downstream: Commit, *, window_size_secs: int = 60
) -> Commit | None:
    """Find the most recent commit on upstream that has been merged into downstream."""
    reachable = WindowedReachable(downstream, window_size_secs=window_size_secs)
    commit: Commit | None = upstream
    while commit and commit not in reachable:
        try:
            commit = commit.first_parent
        except MissingCommit:
            return None
    return commit
