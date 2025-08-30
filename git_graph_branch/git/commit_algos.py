from functools import total_ordering
from heapq import heappop, heappush
from typing import Any, Iterator

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


class CommitSet:
    """Stores a set of commits, with O(1) access to the newest commit."""

    def __init__(self, commit: Commit):
        self._commits = {commit}
        self._in_commits = [ChronoCommit(commit)]
        self.last_added: Commit | None = commit

    def __contains__(self, commit: Commit) -> bool:
        return commit in self._commits

    def add(self, commit: Commit | None) -> None:
        """Add a commit to the window."""
        self.last_added = commit
        if commit:
            self._commits.add(commit)
            heappush(self._in_commits, ChronoCommit(commit))

    def remove_newer_than(self, commit_date: int) -> None:
        """Prune all commits newer than commit_date."""
        while self._in_commits and self._in_commits[0].is_newer_than(commit_date):
            self._commits.remove(self._in_commits[0].commit)
            heappop(self._in_commits)


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
