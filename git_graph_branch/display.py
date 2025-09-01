# coding=utf-8
from argparse import Namespace
from enum import Enum
from typing import Any, Iterable

from ansi import color

from .dag import NodeArt
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


def compute_branch_color(b: Branch) -> object | None:
    if b.is_head:
        return color.fg.boldmagenta
    if isinstance(b.upstream, Branch) and not any(
        unmerged_commits(b.upstream.commit, b.commit)
    ):
        # If all commits are merged into the upstream branch, and the upstream is not a remote branch,
        # display the branch in grey to show it is safe to delete.
        return color.fg.grey
    return None


def print_branch(
    art: NodeArt, b: Branch, config: Config, parents: Iterable[Branch]
) -> None:
    print(f"{art}  ", end="")
    reset = False
    if config.color:
        branch_color = compute_branch_color(b)
        if branch_color is not None:
            print(branch_color, end="")
            reset = True
    print(b, end="")
    if reset:
        print(color.fx.reset, end="")
    if config.remote_icons:
        print(SYNC_STATUS_ICON[remote_sync_status(b)], end="")

    unmerged = compute_unmerged(b, parents)
    if unmerged > 0:
        if config.color:
            print(color.fg.boldred, end="")
        print(f" [{unmerged} unmerged]", end="")
        if config.color:
            print(color.fx.reset, end="")
    print()
