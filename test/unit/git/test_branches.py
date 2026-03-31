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


def test_packed_branches(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-b", "a"])
    git_test_commit()
    git_test_commit()
    git_test_commit()
    check_call(["git", "gc"])
    check_call(["git", "checkout", "-b", "b"])
    git_test_commit()
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])

    bs = set(branches())

    assert bs == {Branch("main"), Branch("a"), Branch("b")}


def test_packed_branch_not_duplicated_with_loose_ref(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-b", "feature"])
    git_test_commit()
    check_call(
        ["git", "gc"]
    )  # packs refs, so "feature" is now in packed-refs at old_hash

    new_hash = git_test_commit()  # advance "feature", creating a loose ref

    bs = [b for b in branches() if b.name == "feature"]
    assert len(bs) == 1
    assert bs[0].commit.hash == new_hash
