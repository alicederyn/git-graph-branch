from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, Commit

from .utils import git_test_commit


def test_simple_names(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", "feature"])

    assert Branch("main").commit == Commit(commit)
    assert Branch("feature").commit == Commit(commit)


def test_hash_in_name(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", "foo#bar"])
    assert Branch("foo#bar").commit == Commit(commit)


def test_quote_in_name(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", 'foo"bar'])
    assert Branch('foo"bar').commit == Commit(commit)


def test_slash_in_name(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    assert Branch("bug/101").commit == Commit(commit)
