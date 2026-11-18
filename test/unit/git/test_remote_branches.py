from pathlib import Path
from subprocess import check_call

from git_graph_branch.git.branch import RemoteBranch, remote_branches

from .utils import git_test_commit


def test_remote_branches_are_loose_and_packed(worktree: Path) -> None:
    git_test_commit()
    check_call(["git", "update-ref", "refs/remotes/origin/packed", "main"])
    check_call(["git", "pack-refs", "--all"])
    check_call(["git", "update-ref", "refs/remotes/origin/loose", "main"])
    check_call(["git", "update-ref", "refs/remotes/origin/packed", "main"])

    assert remote_branches() == {
        RemoteBranch("origin", "packed"),
        RemoteBranch("origin", "loose"),
    }


def test_remote_head_and_lock_files_are_not_branches(
    worktree: Path, repo: Path
) -> None:
    git_test_commit()
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"]
    )
    (repo / ".git" / "refs" / "remotes" / "origin" / "x.lock").write_text("")

    assert remote_branches() == {RemoteBranch("origin", "main")}


def test_remote_branches_are_cached(worktree: Path) -> None:
    """All reads of the store in one calculation must find the same branches."""
    assert remote_branches() is remote_branches()
