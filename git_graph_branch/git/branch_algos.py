from heapq import heapify, heappop, heappush
from typing import Iterator

from git_graph_branch.dag import DAG

from .branch import Branch, RemoteBranch
from .commit import Commit
from .commit_algos import (
    CommitMap,
    CommitSet,
    CommitSetMultimap,
    merge_reverse_chronological,
    range,
)
from .reflog import ReflogEntry


class ChronoReflog:
    def __init__(
        self, branch: Branch, *, iter: Iterator[ReflogEntry] | None = None
    ) -> None:
        self.branch = branch
        self._iter = iter or branch.reflog()
        self.reflog = next(self._iter)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ChronoReflog)
            and self.branch == other.branch
            and self.reflog == other.reflog
        )

    def __lt__(self, other: "ChronoReflog") -> bool:
        return self.reflog.timestamp > other.reflog.timestamp

    def next(self) -> "ChronoReflog | None":
        try:
            iter = self._iter
        except AttributeError:
            raise RuntimeError("ChronoReflog.next can only be called once")
        del self.__dict__["_iter"]
        try:
            return ChronoReflog(self.branch, iter=iter)
        except StopIteration:
            return None


class WindowedFirstBranchReferences:
    """Tracks the first branch that ever referenced a commit.

    A branch is considered to have referenced a commit when it has a reflog from which
    the commit is reachable, and the first reference is determined by the reflog time.

    Must be accessed in approximately reverse-chronological order, as each access
    will shift the window of visibility backwards.
    """

    def __init__(self, branches: list[Branch], *, window_size_secs: int = 60) -> None:
        self.window_size_secs = window_size_secs

        # Yet-to-be-processed reflogs
        self.reflogs = [ChronoReflog(b) for b in branches]
        heapify(self.reflogs)

        # Yet-to-be-processed commits
        self.commits = CommitSet()

        # For each commit seen, store the branch with the oldest
        # reflog that the commit is reachable from
        self.refs: CommitMap[ChronoReflog] = CommitMap()

    def _add_commit_todo(self, reflog: ChronoReflog, commit: Commit) -> None:
        if commit not in self.refs:
            self.refs[commit] = reflog
            self.commits.add(commit)
        elif reflog > self.refs[commit]:
            self.refs[commit] = reflog

    def _add_reflogs_after(self, ts: int) -> None:
        while self.reflogs and self.reflogs[0].reflog.timestamp >= ts:
            reflog = heappop(self.reflogs)
            next_reflog = reflog.next()
            if next_reflog:
                heappush(self.reflogs, next_reflog)
            self._add_commit_todo(reflog, reflog.reflog.commit)

    def _add_commits_after(self, ts: int) -> None:
        while self.commits and self.commits.peek().commit_date >= ts:
            commit = self.commits.pop()
            if commit.first_parent is not None:
                self._add_commit_todo(self.refs[commit], commit)

    def get(self, key: Commit) -> Branch | None:
        target_ts = key.commit_date - self.window_size_secs
        self._add_reflogs_after(target_ts)
        self._add_commits_after(target_ts)
        self.refs.remove_newer_than(key.commit_date + self.window_size_secs)
        return self.refs[key].branch if key in self.refs else None


def upstream_range(branch: Branch) -> Iterator[tuple[Commit, Branch]]:
    if branch.upstream is not None:
        for commit in range(branch.upstream.commit, branch.commit):
            yield (commit, branch)


def merge_commits(branches: list[Branch]) -> Iterator[tuple[Commit, Branch]]:
    """Yields a reverse chronological merge history for branches.

    Each commit merged into the first-parent route between each branch and its upstream
    will be yielded, ordered by the merged commit, most recent first.
    """
    merge_commits: CommitSetMultimap[Branch] = CommitSetMultimap()

    for commit, branch in merge_reverse_chronological(
        upstream_range(branch) for branch in branches
    ):
        while merge_commits and merge_commits.peek().commit_date > commit.commit_date:
            yield merge_commits.popitem()

        for merge_parent in commit.available_merge_parents():
            merge_commits.add(merge_parent, branch)

    while merge_commits:
        yield merge_commits.popitem()


def merge_histories(
    branches: list[Branch], *, window_size_secs: int = 60
) -> Iterator[tuple[Branch, Branch]]:
    """Yields a reverse chronological join history for branches.

    Each branch merged into the first-parent route between each branch and its upstream,
    plus the upstream branch, will be yielded, most recent first. Ordering is determined
    by the timestamp of the merged/upstream commit.
    """
    references = WindowedFirstBranchReferences(
        branches, window_size_secs=window_size_secs
    )
    merges = (
        (commit, (merged_branch, branch))
        for (commit, branch) in merge_commits(branches)
        if (merged_branch := references.get(commit))
    )
    upstreams = [
        (upstream.commit, (upstream, downstream))
        for downstream in branches
        if (upstream := downstream.upstream) and not isinstance(upstream, RemoteBranch)
    ]
    upstreams.sort(key=lambda entry: entry[0].commit_date, reverse=True)

    for _, join in merge_reverse_chronological([merges, upstreams]):
        yield join


def compute_branch_dag(
    branches: list[Branch], *, window_size_secs: int = 60
) -> DAG[Branch]:
    """Compute a DAG of merge and upstream connections between branches.

    If the real graph contains a cycle, it is broken by arbitrarily removing the
    oldest links in the graph that are causing cycles. For instance, if branch
    A is branch B's upstream, but B was merged into A after it was forked from
    it, it will be shown as upstream of A, not the other way around.
    """
    return DAG(branches, merge_histories(branches, window_size_secs=window_size_secs))
