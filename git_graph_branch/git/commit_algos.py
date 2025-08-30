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


def all_parents(commit: Commit, *, window_size_secs: int = 60) -> Iterator[Commit]:
    """Yield all parents of a commit in chronological order (newest first)."""
    heap = [ChronoCommit(commit)]
    seen = CommitSet(commit)

    while heap:
        current = heappop(heap).commit
        seen.remove_newer_than(current.commit_date + window_size_secs)
        yield current

        for parent in current.available_parents():
            if parent not in seen:
                seen.add(parent)
                heappush(heap, ChronoCommit(parent))


def extend_window_with_first_parents(window: CommitSet, commit_date: int) -> None:
    commit = window.last_added
    while commit and commit.commit_date > commit_date:
        window.add(commit.first_parent)
        commit = window.last_added


def last_merged_commit(
    upstream: Commit, downstream: Commit, *, window_size_secs: int = 60
) -> Commit | None:
    """Find the most recent commit on downstream that has been merged into upstream."""

    upstream_window = CommitSet(upstream)

    for downstream_commit in all_parents(downstream, window_size_secs=window_size_secs):
        try:
            upstream_window.remove_newer_than(
                downstream_commit.commit_date + window_size_secs
            )
            extend_window_with_first_parents(
                upstream_window, downstream_commit.commit_date - window_size_secs
            )
            if downstream_commit in upstream_window:
                return downstream_commit
        except MissingCommit:
            break

    return None
