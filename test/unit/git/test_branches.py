from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, branches

from .utils import git_test_commit


def test_branches_empty_repo(repo: Path) -> None:
    bs = tuple(branches())
    assert bs == ()


def test_simple_names(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "feature"])
    bs = set(branches())
    assert bs == {Branch("main"), Branch("feature")}


def test_hash_in_name(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "foo#bar"])
    bs = set(branches())
    assert bs == {Branch("main"), Branch("foo#bar")}


def test_quote_in_name(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", 'foo"bar'])
    bs = set(branches())
    assert bs == {Branch("main"), Branch('foo"bar')}


def test_slash_in_name(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    bs = set(branches())
    assert bs == {Branch("main"), Branch("bug/101")}
