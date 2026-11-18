import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from pathlib import Path
from subprocess import check_call
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from git_graph_branch.display import PrStatus, pr_status
from git_graph_branch.git import Branch
from git_graph_branch.github import transport
from git_graph_branch.nix.fact import (
    Fact,
    release_moot_facts,
    report_calculation,
    session,
)
from test.conftest import cache_clear_fns


@pytest.fixture(autouse=True)
def post() -> Iterator[AsyncMock]:
    """Answer that each repository does not exist."""

    async def respond(
        endpoint: object, body: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        prefixes = {name.split("_", 1)[0] for name in body["variables"]}
        return {"data": {f"{p}_repository": None for p in prefixes}}, {}

    with patch.object(transport, "post", new=AsyncMock(side_effect=respond)) as mock:
        yield mock


@pytest.fixture(autouse=True)
def MIN_BATCH_INTERVAL(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "MIN_BATCH_INTERVAL", 0.0)


@pytest.fixture
async def watching() -> AsyncIterator[None]:
    async with asyncio.TaskGroup() as task_group:
        with session(task_group):
            yield


@pytest.fixture
def feature(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Branch:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    check_call(["git", "commit", "--allow-empty", "-m", "first"])
    check_call(["git", "checkout", "-b", "feature"])
    check_call(["git", "remote", "add", "origin", "git@github.com:o/n.git"])
    check_call(["git", "config", "remote.pushdefault", "origin"])
    return Branch("feature")


class Frames:
    """Calculate reports as the watch loop does: each change nixes the last
    report, and moot facts are released when a report is complete."""

    def __init__(self, branch: Branch) -> None:
        self.branch = branch
        self.report: Fact | None = None

    async def next(self, branch: Branch | None = None) -> PrStatus:
        if self.report is not None:
            self.report.nix()
        for cache_clear in cache_clear_fns:
            cache_clear()
        with report_calculation() as self.report:
            status = await pr_status(branch or self.branch, wait=False)
        release_moot_facts()
        await asyncio.sleep(0.05)
        return status


def is_loading(status: PrStatus) -> bool:
    return status.check_loading or status.review_loading or status.ended_loading


def push() -> None:
    check_call(["git", "update-ref", "refs/remotes/origin/feature", "feature"])


async def test_first_push_shows_no_pr_without_loading(
    watching: None, feature: Branch
) -> None:
    frames = Frames(feature)
    await frames.next()
    await frames.next()
    push()

    status = await frames.next()

    assert not is_loading(status)
    assert status.has_pr is False
    assert status.new_pr_url == "https://github.com/o/n/pull/new/feature"


async def test_later_push_shows_no_pr_without_loading(
    watching: None, feature: Branch
) -> None:
    push()
    frames = Frames(feature)
    await frames.next()
    await frames.next()
    check_call(["git", "commit", "--allow-empty", "-m", "second"])
    push()

    assert not is_loading(await frames.next())


async def test_first_push_of_a_branch_with_a_remote_upstream_shows_no_pr(
    watching: None, feature: Branch
) -> None:
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])
    frames = Frames(feature)
    await frames.next()
    await frames.next()
    push()

    status = await frames.next()

    assert not is_loading(status)
    assert status.new_pr_url == "https://github.com/o/n/pull/new/feature"


async def test_branch_pushed_before_the_first_report_is_loading(
    watching: None, feature: Branch
) -> None:
    push()

    assert (await Frames(feature).next()).check_loading


async def test_first_push_with_upstream_set_by_the_push_shows_no_pr(
    watching: None, feature: Branch
) -> None:
    check_call(["git", "config", "--unset", "remote.pushdefault"])
    frames = Frames(feature)
    await frames.next()
    await frames.next()
    push()
    await frames.next()
    check_call(["git", "branch", "--set-upstream-to", "origin/feature"])

    assert not is_loading(await frames.next())


async def test_checkout_of_a_branch_fetched_at_the_same_time_is_loading(
    watching: None, feature: Branch
) -> None:
    frames = Frames(feature)
    await frames.next()
    await frames.next()
    check_call(["git", "update-ref", "refs/remotes/origin/colleague", "main"])
    check_call(["git", "branch", "--track", "colleague", "origin/colleague"])

    assert (await frames.next(Branch("colleague"))).check_loading
