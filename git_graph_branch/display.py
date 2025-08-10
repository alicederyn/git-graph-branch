# coding=utf-8
from argparse import Namespace
from enum import Enum
from typing import Any

from ansi import color

from .dag import NodeArt
from .git.branch import Branch, RemoteBranch
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


def print_branch(art: NodeArt, b: Branch, config: Config) -> None:
    print(f"{art}  ", end="")
    reset = False
    if config.color and b.is_head:
        print(color.fg.magenta, end="")
        reset = True
    print(b, end="")
    if reset:
        print(color.fx.reset, end="")
    if config.remote_icons:
        print(SYNC_STATUS_ICON[remote_sync_status(b)], end="")
    print()
