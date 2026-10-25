# coding=utf-8
import asyncio
import os
from argparse import Namespace
from enum import Enum
from typing import Any, Iterable, NamedTuple

from prompt_toolkit.formatted_text import OneStyleAndTextTuple, StyleAndTextTuples

from .dag import NodeArt, layout
from .git import branches, compute_branch_dag, worktree_branches
from .git.branch import Branch, RemoteBranch
from .git.commit_algos import unmerged_commits
from .github import CheckStatus, ReviewStatus, pr_check_status, pr_review_status
from .links import Link


class Config(Namespace):
    color: bool
    is_tty: bool
    remote_icons: bool
    pr_icons: bool
    watch: bool = False
    poll_every: float = 1.0

    def __init__(self, *, is_tty: bool = False, **kwargs: Any) -> None:
        # https://no-color.org: NO_COLOR, if set and not empty, turns off
        # colour by default, but an explicit --color still wins
        no_color = bool(os.environ.get("NO_COLOR"))
        defaults = {
            "color": is_tty and not no_color,
            "remote_icons": is_tty,
            "pr_icons": is_tty,
        }
        super().__init__(**(defaults | kwargs), is_tty=is_tty)


class PrStatus(NamedTuple):
    check: CheckStatus | None = None
    review: ReviewStatus | None = None
    failed: bool = False
    """Whether the latest load of either status failed."""
    review_url: str | None = None
    new_pr_url: str | None = None
    """Where to create a PR, once both statuses have loaded with no PR."""
    has_pr: bool | None = None
    """False if both statuses say the branch has no PR, else None if either is not known."""
    review_loading: bool = False
    check_loading: bool = False


class Frame(NamedTuple):
    """One rendering of the repository, and where the current branch is in it."""

    rows: list[StyleAndTextTuples]
    head: int | None


class SyncStatus(Enum):
    NO_REMOTE = "NO_REMOTE"
    OUT_OF_SYNC = "OUT_OF_SYNC"
    IN_SYNC = "IN_SYNC"


SYNC_STATUS_ICON = {
    SyncStatus.NO_REMOTE: "",
    SyncStatus.OUT_OF_SYNC: "🔶",
    SyncStatus.IN_SYNC: "🔷",
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
    downstream = b.downstream
    if downstream:
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


def icon(text: str, url: str | None) -> OneStyleAndTextTuple:
    return ("", text, Link(url)) if url else ("", text)


def status_icons(b: Branch, config: Config, pr_status: PrStatus) -> StyleAndTextTuples:
    """The push and PR status icons.

    🔷 shows only if the branch has no PR, as the review icon takes its place.
    🔌 takes the place of the first status that has not loaded.
    """
    icons: StyleAndTextTuples = []
    if config.remote_icons:
        sync_status = remote_sync_status(b)
        if sync_status == SyncStatus.OUT_OF_SYNC or (
            sync_status == SyncStatus.IN_SYNC and pr_status.has_pr is False
        ):
            icons.append(icon(SYNC_STATUS_ICON[sync_status], pr_status.new_pr_url))
    if pr_status.review_loading:
        icons.append(("", "🔌"))
    elif pr_status.review:
        icons.append(icon(pr_status.review.value, pr_status.review_url))
    if pr_status.check_loading:
        if not pr_status.review_loading:
            icons.append(("", "🔌"))
    elif pr_status.check:
        icons.append(("", pr_status.check.value))
    if pr_status.failed:
        icons.append(("", "⚠️"))
    return icons


def branch_fragments(
    art: NodeArt,
    b: Branch,
    config: Config,
    parents: Iterable[Branch],
    worktree_branches: set[str],
    pr_status: PrStatus,
) -> StyleAndTextTuples:
    fragments: StyleAndTextTuples = [("", f"{art}  "), (branch_style(b), str(b))]
    if b.name in worktree_branches:
        fragments.append(("", " 🌲"))
    if icons := status_icons(b, config, pr_status):
        fragments.append(("", " "))
        fragments.extend(icons)
    unmerged = compute_unmerged(b, parents)
    if unmerged > 0:
        fragments.append(("class:unmerged", f" [{unmerged} unmerged]"))
    return fragments


async def pr_status(branch: Branch, *, wait: bool) -> PrStatus:
    check, review = await asyncio.gather(
        pr_check_status(branch, wait=wait), pr_review_status(branch, wait=wait)
    )
    has_no_pr = check.has_pr is False and review.has_pr is False
    return PrStatus(
        check.status,
        review.status,
        check.failed or review.failed,
        review.url,
        check.url if has_no_pr else None,
        False if has_no_pr else None,
        review.loading,
        check.loading,
    )


async def pr_statuses(config: Config, branches: list[Branch]) -> list[PrStatus]:
    if not config.pr_icons:
        return [PrStatus(has_pr=False)] * len(branches)
    return await asyncio.gather(
        *(pr_status(b, wait=not config.watch) for b in branches)
    )


async def graph_frame(config: Config) -> Frame:
    """Render every branch as one row of styled fragments, and find HEAD's row.

    This reads the filesystem, so it must be called inside a nix report
    calculation. The frame it returns is a snapshot, so redrawing does not touch
    the filesystem or the network.
    """
    dag = compute_branch_dag(list(branches()))
    art_and_branches = layout(dag, key=lambda b: (b.timestamp, b.name))
    wt_branches = worktree_branches()
    statuses = await pr_statuses(config, [b for _, b in art_and_branches])
    rows = [
        branch_fragments(art, b, config, dag.parents(b), wt_branches, status)
        for (art, b), status in zip(art_and_branches, statuses)
    ]
    head = next((i for i, (_, b) in enumerate(art_and_branches) if b.is_head), None)
    return Frame(rows, head)
