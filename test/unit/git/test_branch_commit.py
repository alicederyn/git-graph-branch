from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, Commit

from .utils import head_hash


def head_commit() -> Commit:
    return Commit(head_hash())


def test_simple_names(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Blank commit"])
    main_commit = head_commit()
    check_call(["git", "checkout", "main", "-b", "feature"])
    feature_commit = head_commit()

    assert Branch("main").commit == main_commit
    assert Branch("feature").commit == feature_commit


def test_hash_in_name(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Blank commit"])
    check_call(["git", "checkout", "main", "-b", "foo#bar"])
    commit = head_commit()
    assert Branch("foo#bar").commit == commit


def test_quote_in_name(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Blank commit"])
    check_call(["git", "checkout", "main", "-b", 'foo"bar'])
    commit = head_commit()
    assert Branch('foo"bar').commit == commit


def test_slash_in_name(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Blank commit"])
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    commit = head_commit()
    assert Branch("bug/101").commit == commit
