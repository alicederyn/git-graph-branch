import os
from pathlib import Path
from subprocess import check_call

import pytest

from git_graph_branch.git.branch import worktree_branches

from .utils import git_test_commit


def test_no_worktrees(worktree: Path) -> None:
    git_test_commit()
    assert worktree_branches() == set()


@pytest.mark.usefixtures("repo")
def test_linked_worktree_branch_included(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    git_test_commit()
    wt = tmp_path_factory.mktemp("wt") / "linked"
    check_call(["git", "worktree", "add", str(wt), "-b", "feature", "main"])
    assert worktree_branches() == {"feature"}


@pytest.mark.usefixtures("repo")
def test_linked_worktree_detached_head_excluded(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    commit = git_test_commit()
    wt = tmp_path_factory.mktemp("wt") / "linked"
    check_call(["git", "worktree", "add", "--detach", str(wt), commit])
    assert worktree_branches() == set()


@pytest.mark.usefixtures("repo")
def test_current_worktree_excluded(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    git_test_commit()
    wt = tmp_path_factory.mktemp("wt") / "linked"
    check_call(["git", "worktree", "add", str(wt), "-b", "feature", "main"])
    os.chdir(wt)
    result = worktree_branches()
    # From the linked worktree, the main worktree's branch ("main") is "other"
    assert "main" in result
    # The linked worktree's own branch should NOT appear
    assert "feature" not in result


@pytest.mark.usefixtures("repo")
def test_multiple_worktrees(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    git_test_commit()
    wt1 = tmp_path_factory.mktemp("wt1") / "linked1"
    wt2 = tmp_path_factory.mktemp("wt2") / "linked2"
    check_call(["git", "worktree", "add", str(wt1), "-b", "feature-a", "main"])
    check_call(["git", "worktree", "add", str(wt2), "-b", "feature-b", "main"])
    assert worktree_branches() == {"feature-a", "feature-b"}
