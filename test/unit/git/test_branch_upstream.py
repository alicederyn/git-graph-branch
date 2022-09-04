from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch

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
    b = Branch("main")
    assert b.upstream is None


def test_upstream_is_main(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-tb", "feature"])
    b = Branch("feature")
    assert b.upstream == Branch("main")


def test_quote_in_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-tb", 'a"b'])
    check_call(["git", "checkout", "-tb", "feature"])
    b = Branch("feature")
    assert b.upstream == Branch('a"b')


def test_hash_in_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-tb", "a#b"])
    check_call(["git", "checkout", "-tb", "feature"])
    b = Branch("feature")
    assert b.upstream == Branch("a#b")
