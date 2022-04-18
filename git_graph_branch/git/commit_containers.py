from functools import total_ordering
from heapq import heappop, heappush, heappushpop
from typing import Any, Iterable

from .commit import Commit, MissingCommit


@total_ordering
class ChronoCommit:
    """Newer commits will compare less than older ones"""

    def __init__(self, commit: Commit):
        self.commit = commit
        self._order = (-commit.timestamp, commit.hash)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ChronoCommit):
            return False
        return self.commit == other.commit

    def __lt__(self, other: "ChronoCommit") -> bool:
        if not isinstance(other, ChronoCommit):
            return NotImplemented
        return self._order < other._order


class CommitQueue:
    """Heap of commits, newest first"""

    def __init__(self) -> None:
        self._heap: list[ChronoCommit] = []

    def __len__(self) -> int:
        return len(self._heap)

    def peek(self) -> Commit | None:
        return self._heap[0].commit if self._heap else None

    def push(self, commit: Commit | None) -> None:
        if commit:
            heappush(self._heap, ChronoCommit(commit))

    def pop(self) -> Commit | None:
        head = heappop(self._heap)
        return head.commit if head else None

    def pushpop(self, commit: Commit | None) -> Commit | None:
        if not commit:
            return self.pop()
        head = heappushpop(self._heap, ChronoCommit(commit))
        return head.commit if head else None


def first_parent_if_not_missing(commit: Commit) -> Commit | None:
    try:
        parent = commit.first_parent
        if parent:
            parent.timestamp  # Force an exception if commit missing
        return parent
    except MissingCommit:
        return None


class ReachableCommits:
    """Maintains a moveable window of reachable commits

    The window can be moved backwards in time, at which point each commit
    will be traced back through its first-parent history, as far as is
    available.

    Some commits outside the window may be visible, and some commits inside
    the window may not be visible if they are only reachable by a commit
    earlier than the earliest point of the window, but if the window has
    been rewound to a commit, a membership test for that commit should
    not fail if the commit is reachable.
    """

    def __init__(self, commits: Iterable[Commit], *, window_size_secs: int = 60):
        self.window_size_secs = window_size_secs
        self._seen: set[Commit] = set()
        self._in_seen = CommitQueue()
        self._todo = CommitQueue()
        for commit in commits:
            if commit not in self._seen:
                self._seen.add(commit)
                self._in_seen.push(commit)
                self._todo.push(commit)

    def __bool__(self) -> bool:
        return bool(self._seen)

    def __contains__(self, commit: Commit) -> bool:
        return commit in self._seen

    def _prune_to_timestamp(self, timestamp: int) -> None:
        while (head := self._in_seen.peek()) and head.timestamp > timestamp:
            self._in_seen.pop()
            self._seen.remove(head)

    def rewind_to(self, commit: Commit) -> None:
        try:
            min_timestamp = commit.timestamp - self.window_size_secs
        except MissingCommit:
            return

        while (next := self._todo.peek()) and next.timestamp >= min_timestamp:
            self._prune_to_timestamp(next.timestamp + 2 * self.window_size_secs)
            parent = first_parent_if_not_missing(next)
            if parent and parent not in self._seen:
                self._todo.pushpop(parent)
                self._seen.add(parent)
                self._in_seen.push(parent)
            else:
                self._todo.pop()

        self._prune_to_timestamp(commit.timestamp + self.window_size_secs)
