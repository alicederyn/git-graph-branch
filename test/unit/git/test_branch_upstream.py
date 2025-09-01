from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, RemoteBranch

from .utils import git_test_commit


def test_main_no_upstream(repo: Path) -> None:
    git_test_commit()
    b = Branch("main")
    assert b.upstream is None


def test_main_remote_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(
        ["git", "remote", "add", "origin", "git@github.com:alicederyn/example.git"]
    )
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    check_call(["git", "branch", "--set-upstream-to", "origin/main"])
    b = Branch("main")
    assert b.upstream == RemoteBranch("origin", "main")


def test_upstream_is_main(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "feature"])
    b = Branch("feature")
    assert b.upstream == Branch("main")


def test_quote_in_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", 'a"b'])
    check_call(["git", "checkout", "-t", "-b", "feature"])
    b = Branch("feature")
    assert b.upstream == Branch('a"b')


def test_hash_in_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "a#b"])
    check_call(["git", "checkout", "-t", "-b", "feature"])
    b = Branch("feature")
    assert b.upstream == Branch("a#b")


def test_deleted_remote_upstream(repo: Path) -> None:
    check_call(["git", "checkout", "-t", "-b", "a"])
    git_test_commit()
    check_call(
        ["git", "remote", "add", "origin", "git@github.com:alicederyn/example.git"]
    )
    check_call(["git", "update-ref", "refs/remotes/origin/a", "a"])
    check_call(["git", "branch", "--set-upstream-to", "origin/a"])
    b = Branch("a")
    assert b.upstream == RemoteBranch("origin", "a")

    # Replicate a state we can get into with a `git fetch origin` call
    Path(".git", "refs", "remotes", "origin", "a").unlink()

    assert b.upstream is None


def test_renamed_local_upstream(repo: Path) -> None:
    check_call(["git", "checkout", "-t", "-b", "a"])
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "b"])
    check_call(["git", "branch", "-d", "a"])

    b = Branch("b")

    assert b.upstream is None
