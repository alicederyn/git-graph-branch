from pathlib import Path

from git_graph_branch.git import Commit, RemoteBranch

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

    assert RemoteBranch("origin", "main").commit == Commit(commit2)
    assert RemoteBranch("upstream", "main").commit == Commit(commit1)


def test_commit_slash_in_name(repo: Path) -> None:
    commit1 = git_test_commit()
    git_test_commit()
    git_remote_repo("origin", **{"foo/bar": commit1})

    assert RemoteBranch("origin", "foo/bar").commit == Commit(commit1)
