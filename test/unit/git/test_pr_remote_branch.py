from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, RemoteBranch
from git_graph_branch.github.remote import PushTarget, pr_remote_branch, push_target

from .utils import git_test_commit


def add_remote(name: str) -> None:
    check_call(["git", "remote", "add", name, f"git@github.com:{name}/example.git"])


def track_main_with_push_remote(push_remote: str) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-b", "feature"])
    add_remote("origin")
    add_remote(push_remote)
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])
    check_call(["git", "config", "remote.pushdefault", push_remote])


def test_pushdefault_branch_is_preferred_to_remote_upstream(worktree: Path) -> None:
    track_main_with_push_remote("fork")
    check_call(["git", "update-ref", "refs/remotes/fork/feature", "feature"])

    assert pr_remote_branch(Branch("feature")) == RemoteBranch("fork", "feature")


def test_remote_upstream_before_the_first_push(worktree: Path) -> None:
    track_main_with_push_remote("fork")

    assert pr_remote_branch(Branch("feature")) == RemoteBranch("origin", "main")


def test_remote_upstream_without_push_target(worktree: Path) -> None:
    git_test_commit()
    add_remote("origin")
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])

    assert pr_remote_branch(Branch("main")) == RemoteBranch("origin", "main")
    assert push_target(Branch("main")) == PushTarget("origin", "main")


def test_local_upstream_has_no_pr_remote_branch(worktree: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "feature"])

    assert pr_remote_branch(Branch("feature")) is None
    assert push_target(Branch("feature")) is None


def test_push_target_before_the_first_push(worktree: Path) -> None:
    track_main_with_push_remote("fork")

    target = push_target(Branch("feature"))

    assert target == PushTarget("fork", "feature")
    assert target.tracking is None


def test_pruned_upstream_is_a_push_target_but_not_a_status_branch(
    worktree: Path,
) -> None:
    git_test_commit()
    add_remote("origin")
    check_call(["git", "config", "branch.main.remote", "origin"])
    check_call(["git", "config", "branch.main.merge", "refs/heads/feature"])

    assert pr_remote_branch(Branch("main")) is None
    assert push_target(Branch("main")) == PushTarget("origin", "feature")
