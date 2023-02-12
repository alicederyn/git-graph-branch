from pathlib import Path
from subprocess import check_call

import pytest

from git_graph_branch.git import Commit, RemoteBranch
from git_graph_branch.ixnay import SingleUseNixer
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver

from .utils import git_remote_repo, git_test_commit


def test_init_one_arg(repo: Path) -> None:
    ref = repo / ".git" / "refs" / "remotes" / "upstream" / "main"
    remote = RemoteBranch(ref)

    assert remote._ref == ref
    assert str(remote) == "upstream/main"
    assert repr(remote) == "git.RemoteBranch('upstream', 'main')"


def test_init_one_arg_branch_with_a_slash(repo: Path) -> None:
    ref = repo / ".git" / "refs" / "remotes" / "origin" / "features" / "foobar"
    remote = RemoteBranch(ref)

    assert remote._ref == ref
    assert str(remote) == "origin/features/foobar"
    assert repr(remote) == "git.RemoteBranch('origin', 'features/foobar')"


def test_init_two_args(repo: Path) -> None:
    remote = RemoteBranch("upstream", "main")

    assert remote._ref == repo / ".git" / "refs" / "remotes" / "upstream" / "main"
    assert str(remote) == "upstream/main"
    assert repr(remote) == "git.RemoteBranch('upstream', 'main')"


def test_init_two_args_branch_with_a_slash(repo: Path) -> None:
    remote = RemoteBranch("origin", "features/foobar")

    assert (
        remote._ref
        == repo / ".git" / "refs" / "remotes" / "origin" / "features" / "foobar"
    )
    assert str(remote) == "origin/features/foobar"
    assert repr(remote) == "git.RemoteBranch('origin', 'features/foobar')"


def test_commit(repo: Path) -> None:
    commit1 = git_test_commit()
    commit2 = git_test_commit()
    git_test_commit()
    git_remote_repo("upstream", main=commit1)
    git_remote_repo("origin", main=commit2)

    assert RemoteBranch("origin", "main").commit(SingleUseNixer()) == Commit(commit2)
    assert RemoteBranch("upstream", "main").commit(SingleUseNixer()) == Commit(commit1)


def test_commit_slash_in_name(repo: Path) -> None:
    commit1 = git_test_commit()
    git_test_commit()
    git_remote_repo("origin", **{"foo/bar": commit1})

    assert RemoteBranch("origin", "foo/bar").commit(SingleUseNixer()) == Commit(commit1)


@pytest.mark.parametrize("branch_name", ["main", "foo/bar", 'baz"bam'])
def test_commit_invalidation(
    branch_name: str, repo: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    branch = RemoteBranch("origin", branch_name)
    commit1 = git_test_commit()
    commit2 = git_test_commit()
    git_remote_repo("origin", **{branch_name: commit1})
    assert branch.commit(nixer) == Commit(commit1)
    check_call(["git", "update-ref", f"refs/remotes/origin/{branch_name}", commit2])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    assert branch.commit(FakeNixer()) == Commit(commit2)
