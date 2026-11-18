import asyncio
from collections.abc import AsyncIterator, Iterator, Mapping
from pathlib import Path
from subprocess import check_call
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from git_graph_branch.display import pr_status
from git_graph_branch.git import Branch
from git_graph_branch.github import transport
from git_graph_branch.nix.fact import report_calculation, session
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


async def test_first_push_shows_no_pr_without_loading(
    watching: None, feature: Branch
) -> None:
    for _ in range(2):
        with report_calculation():
            await pr_status(feature, wait=False)
        await asyncio.sleep(0.05)
    check_call(["git", "update-ref", "refs/remotes/origin/feature", "feature"])
    for cache_clear in cache_clear_fns:
        cache_clear()

    with report_calculation():
        status = await pr_status(feature, wait=False)

    assert not (status.check_loading or status.review_loading or status.ended_loading)
    assert status.has_pr is False
    assert status.new_pr_url == "https://github.com/o/n/pull/new/feature"


async def test_later_push_shows_no_pr_without_loading(
    watching: None, feature: Branch
) -> None:
    check_call(["git", "update-ref", "refs/remotes/origin/feature", "feature"])
    for _ in range(2):
        with report_calculation():
            await pr_status(feature, wait=False)
        await asyncio.sleep(0.05)
    check_call(["git", "commit", "--allow-empty", "-m", "second"])
    check_call(["git", "update-ref", "refs/remotes/origin/feature", "feature"])
    for cache_clear in cache_clear_fns:
        cache_clear()

    with report_calculation():
        status = await pr_status(feature, wait=False)

    assert not (status.check_loading or status.review_loading or status.ended_loading)
