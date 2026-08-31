# coding=utf-8
from argparse import Namespace
from enum import Enum
from typing import Any, Iterable

from prompt_toolkit.formatted_text import StyleAndTextTuples

from .dag import NodeArt, layout
from .git import branches, compute_branch_dag, worktree_branches
from .git.branch import Branch, RemoteBranch
from .git.commit_algos import unmerged_commits
from .git.config import remote_push_default


class Config(Namespace):
    color: bool
    is_tty: bool
    remote_icons: bool
    watch: bool = False
    poll_every: float = 1.0

    def __init__(self, *, is_tty: bool = False, **kwargs: Any) -> None:
        defaults = {"color": is_tty, "remote_icons": is_tty}
        super().__init__(**(kwargs | defaults), is_tty=is_tty)


class SyncStatus(Enum):
    NO_REMOTE = "NO_REMOTE"
    OUT_OF_SYNC = "OUT_OF_SYNC"
    IN_SYNC = "IN_SYNC"


SYNC_STATUS_ICON = {
    SyncStatus.NO_REMOTE: "",
    SyncStatus.OUT_OF_SYNC: " 🔶",
    SyncStatus.IN_SYNC: " 🔷",
}


def remote_sync_status(b: Branch) -> SyncStatus:
    """Returns whether a branch is in sync with its upstream and downstream remotes.

    Only the upstream and pushdefault remotes are considered.
    If the upstream remote commit date is newer, the branch is out of sync.
    If the downstream remote has a different commit, the branch is out of sync.
    If neither exist, the branch has no remote.
    Otherwise the branch is in sync.
    """
    # TODO: Check whether the upstream commit is in the history of the commit,
    # not just whether it is older.
    has_remote = False
    if isinstance(b.upstream, RemoteBranch):
        has_remote = True
        if b.upstream.commit.commit_date > b.commit.commit_date:
            return SyncStatus.OUT_OF_SYNC
    push_remote = remote_push_default()
    if push_remote:
        downstream = RemoteBranch(push_remote, b.name)
        if downstream.exists():
            has_remote = True
            if downstream.commit != b.commit:
                return SyncStatus.OUT_OF_SYNC
    return SyncStatus.IN_SYNC if has_remote else SyncStatus.NO_REMOTE


def compute_unmerged(b: Branch, parents: Iterable[Branch]) -> int:
    parent_commits = [p.commit for p in parents]
    return sum(1 for _ in unmerged_commits(b.commit, *parent_commits))


def branch_style(b: Branch) -> str:
    if b.is_head:
        return "class:branch.head"
    if isinstance(b.upstream, Branch) and not any(
        unmerged_commits(b.upstream.commit, b.commit)
    ):
        # If all commits are merged into the upstream branch, and the upstream is not a remote branch,
        # display the branch in grey to show it is safe to delete.
        return "class:branch.merged"
    return ""


def branch_fragments(
    art: NodeArt,
    b: Branch,
    config: Config,
    parents: Iterable[Branch],
    worktree_branches: set[str],
) -> StyleAndTextTuples:
    fragments: StyleAndTextTuples = [("", f"{art}  "), (branch_style(b), str(b))]
    if b.name in worktree_branches:
        fragments.append(("", " 🌲"))
    if config.remote_icons:
        icon = SYNC_STATUS_ICON[remote_sync_status(b)]
        if icon:
            fragments.append(("", icon))
    unmerged = compute_unmerged(b, parents)
    if unmerged > 0:
        fragments.append(("class:unmerged", f" [{unmerged} unmerged]"))
    return fragments


def graph_rows(config: Config) -> list[StyleAndTextTuples]:
    """Render every branch as one row of styled fragments.

    This reads the filesystem, so it must be called inside the active nix
    cohort. The rows it returns are a snapshot, so redrawing does not touch
    the filesystem.
    """
    dag = compute_branch_dag(list(branches()))
    art_and_branches = layout(dag, key=lambda b: (b.timestamp, b.name))
    wt_branches = worktree_branches()
    return [
        branch_fragments(art, b, config, dag.parents(b), wt_branches)
        for art, b in art_and_branches
    ]
