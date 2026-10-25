from subprocess import check_call

import pytest

from git_graph_branch.display import sync_tooltip
from git_graph_branch.git import Branch

from ..git.utils import git_remote_repo, git_test_commit


@pytest.fixture(autouse=True)
def diverged(repo: object) -> dict[str, str]:
    """feature is two commits ahead of base, and other is one commit ahead."""
    base = git_test_commit()
    check_call(["git", "checkout", "-b", "other"])
    other = git_test_commit(message="other")
    check_call(["git", "checkout", base, "-b", "feature"])
    git_test_commit()
    feature = git_test_commit()
    return {"base": base, "other": other, "feature": feature}


def test_upstream_and_push_branch_that_are_the_same_get_one_line(
    diverged: dict[str, str],
) -> None:
    check_call(["git", "config", "--global", "remote.pushdefault", "origin"])
    git_remote_repo("origin", feature=diverged["other"])
    check_call(["git", "branch", "feature", "--set-upstream-to", "origin/feature"])

    assert sync_tooltip(Branch("feature")) == "origin: 2 ahead, 1 behind"


def test_each_remote_gets_a_line_without_zero_counts(diverged: dict[str, str]) -> None:
    check_call(["git", "config", "--global", "remote.pushdefault", "origin"])
    git_remote_repo("upstream", feature=diverged["base"])
    git_remote_repo("origin", feature=diverged["feature"])
    check_call(["git", "branch", "feature", "--set-upstream-to", "upstream/feature"])

    assert sync_tooltip(Branch("feature")) == "upstream: 2 ahead"
