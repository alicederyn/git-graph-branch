from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, RemoteBranch
from git_graph_branch.github.remote import PushTarget, push_target

from .utils import git_test_commit


def add_remote(name: str) -> None:
    check_call(["git", "remote", "add", name, f"git@github.com:{name}/example.git"])


def test_push_target_is_preferred_to_remote_upstream(worktree: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-b", "feature"])
    add_remote("origin")
    add_remote("fork")
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "update-ref", "refs/remotes/fork/feature", "feature"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])
    check_call(["git", "config", "remote.pushdefault", "fork"])

    target = push_target(Branch("feature"))

    assert target == PushTarget("fork", "feature")
    assert target.tracking == RemoteBranch("fork", "feature")


def test_push_target_before_the_first_push(worktree: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-b", "feature"])
    add_remote("origin")
    add_remote("fork")
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])
    check_call(["git", "config", "remote.pushdefault", "fork"])

    target = push_target(Branch("feature"))

    assert target == PushTarget("fork", "feature")
    assert target.tracking is None


def test_remote_upstream_without_push_target(worktree: Path) -> None:
    git_test_commit()
    add_remote("origin")
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])

    assert push_target(Branch("main")) == PushTarget("origin", "main")


def test_local_upstream_has_no_push_target(worktree: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "feature"])

    assert push_target(Branch("feature")) is None
