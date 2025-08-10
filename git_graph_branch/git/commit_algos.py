from functools import total_ordering
from heapq import heapify, heappop, heappush, heapreplace
from typing import Any, Iterable, Iterator

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

    def __lt__(self, other: "ChronoCommit | ChronoNone") -> bool:
        if isinstance(other, ChronoCommit):
            return self._key < other._key
        elif isinstance(other, ChronoNone):
            return True
        return NotImplemented

    def is_newer_than(self, commit_date: int) -> bool:
        return -self._key[0] > commit_date


@total_ordering
class ChronoNone:
    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ChronoNone)

    def __lt__(self, other: "ChronoCommit | ChronoNone") -> bool:
        if isinstance(other, ChronoCommit) or isinstance(other, ChronoNone):
            return False
        return NotImplemented


class CommitWindow:
    """Stores a set of commits in a time window."""

    def __init__(self, commit: Commit, *, window_size_secs: int = 60):
        self._commits = {commit}
        self._in_commits = [ChronoCommit(commit)]
        self.last_added: Commit | None = commit
        self.window_size_secs = window_size_secs

    def __contains__(self, commit: Commit) -> bool:
        return commit in self._commits

    def add(self, commit: Commit | None) -> None:
        self.last_added = commit
        if commit:
            self._commits.add(commit)
            heappush(self._in_commits, ChronoCommit(commit))

    def prune_to(self, commit_date: int) -> None:
        """Prune all commits newer than commit_date."""
        while self._in_commits and self._in_commits[0].is_newer_than(
            commit_date + self.window_size_secs
        ):
            self._commits.remove(self._in_commits[0].commit)
            heappop(self._in_commits)

    def merge(self, window: "CommitWindow") -> None:
        """Does not affect last_added"""
        for commit in window._commits:
            if commit not in self._commits:
                self._commits.add(commit)
                self._in_commits.append(ChronoCommit(commit))
        heapify(self._in_commits)


@total_ordering
class ChronoWindow:
    """Sort windows by their last-added commit

    As windows are mutable, keeps hold of the commit to allow safe
    storage on a heap.
    """

    def __init__(self, window: CommitWindow):
        self.window = window
        self._key: ChronoCommit | ChronoNone = (
            ChronoCommit(window.last_added) if window.last_added else ChronoNone()
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ChronoWindow):
            return False
        return self._key == other._key and self.window == other.window

    def __lt__(self, other: "ChronoWindow") -> bool:
        if not isinstance(other, ChronoWindow):
            return NotImplemented
        if self._key < other._key:
            return True
        elif self._key > other._key:
            return False
        return id(self.window) < id(other.window)


class WindowHeap:
    """A heap of ChronoWindows

    Kept sorted by their last-added commit in reverse chronological order
    """

    def __init__(self, windows: Iterable[CommitWindow]):
        self._windows = [ChronoWindow(window) for window in windows]
        assert self._windows
        heapify(self._windows)

    def __iter__(self) -> Iterator[CommitWindow]:
        return (w.window for w in self._windows)

    def peek_commit(self) -> Commit | None:
        return self._windows[0].window.last_added

    def pop_commit(self, commit: Commit) -> None:
        try:
            parent = commit.first_parent
        except MissingCommit:
            parent = None
        while (window := self._windows[0].window) and window.last_added == commit:
            window.add(parent)
            heapreplace(self._windows, ChronoWindow(window))
        new_commit = self.peek_commit()
        if new_commit:
            for window in self:
                window.prune_to(new_commit.commit_date)


def all_parents(commit: Commit, *, window_size_secs: int = 60) -> Iterator[Commit]:
    """Yield all parents of a commit in chronological order (newest first)."""
    heap = [ChronoCommit(commit)]
    seen = CommitWindow(commit, window_size_secs=window_size_secs)

    while heap:
        current = heappop(heap).commit
        seen.prune_to(current.commit_date)
        yield current

        for parent in current.available_parents():
            if parent not in seen:
                seen.add(parent)
                heappush(heap, ChronoCommit(parent))


def common_ancestor(*commits: Commit) -> Commit | None:
    """Returns the first common ancestor of a list of commits

    Uses the first_parent property of commits. Will return None
    if the common ancestor has not been fetched from the remote
    repository in a shallow clone.
    """
    if not commits:
        return None
    elif len(commits) == 1:
        return commits[0]

    windows = WindowHeap(CommitWindow(commit) for commit in commits)
    while commit := windows.peek_commit():
        if all(commit in window for window in windows):
            return commit
        windows.pop_commit(commit)
    return None


def extend_window_with_first_parents(window: CommitWindow, commit_date: int) -> None:
    commit = window.last_added
    while commit and commit.commit_date > commit_date:
        window.add(commit.first_parent)
        commit = window.last_added


def last_merged_commit(
    upstream: Commit, downstream: Commit, *, window_size_secs: int = 60
) -> Commit | None:
    """Find the most recent commit on downstream that has been merged into upstream."""

    upstream_window = CommitWindow(upstream, window_size_secs=window_size_secs)

    for downstream_commit in all_parents(downstream, window_size_secs=window_size_secs):
        try:
            upstream_window.prune_to(downstream_commit.commit_date)
            extend_window_with_first_parents(
                upstream_window, downstream_commit.commit_date - window_size_secs
            )
            if downstream_commit in upstream_window:
                return downstream_commit
        except MissingCommit:
            break

    return None
