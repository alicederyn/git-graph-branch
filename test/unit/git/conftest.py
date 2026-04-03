import os
from collections.abc import Iterator
from pathlib import Path
from subprocess import check_call

import pytest


@pytest.fixture(params=["regular", "worktree"], ids=["regular", "worktree"])
def worktree(
    request: pytest.FixtureRequest,
    repo: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Path]:
    """The git worktree under test.

    Every git repo has a worktree. This fixture parameterizes tests to run
    in both the main repo's implicit worktree and a linked worktree created
    with ``git worktree add``.
    """
    if request.param == "regular":
        yield repo
        return
    # Worktree mode: create a linked worktree on `main`
    check_call(["git", "commit", "--allow-empty", "-m", "initial"])
    # Detach HEAD so `main` can be checked out in the worktree
    check_call(["git", "checkout", "--detach"])
    worktree_path = tmp_path_factory.mktemp("worktree") / "wt"
    check_call(["git", "worktree", "add", str(worktree_path), "main"])
    os.chdir(worktree_path)
    # Delete the initial commit so the worktree starts empty, like a fresh repo
    check_call(["git", "update-ref", "-d", "refs/heads/main"])
    yield worktree_path
