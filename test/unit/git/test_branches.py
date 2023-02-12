from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, branches
from git_graph_branch.ixnay import SingleUseNixer
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver

from .utils import git_test_commit


def test_branches_empty_repo(repo: Path) -> None:
    bs = tuple(branches(SingleUseNixer()))
    assert bs == ()


def test_simple_names(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "feature"])
    bs = set(branches(SingleUseNixer()))
    assert bs == {Branch("main"), Branch("feature")}


def test_hash_in_name(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "foo#bar"])
    bs = set(branches(SingleUseNixer()))
    assert bs == {Branch("main"), Branch("foo#bar")}


def test_quote_in_name(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", 'foo"bar'])
    bs = set(branches(SingleUseNixer()))
    assert bs == {Branch("main"), Branch('foo"bar')}


def test_slash_in_name(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    bs = set(branches(SingleUseNixer()))
    assert bs == {Branch("main"), Branch("bug/101")}


def test_create_branch_simple_name_invalidates(
    repo: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    git_test_commit()
    bs = set(branches(nixer))
    check_call(["git", "checkout", "main", "-b", "feature"])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    bs = set(branches(FakeNixer()))
    assert bs == {Branch("main"), Branch("feature")}


def test_create_branch_slash_in_name_invalidates(
    repo: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    bs = set(branches(nixer))
    assert bs == {Branch("main"), Branch("bug/101")}
    check_call(["git", "checkout", "main", "-b", "bug/102"])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    bs = set(branches(FakeNixer()))
    assert bs == {Branch("main"), Branch("bug/101"), Branch("bug/102")}


def test_delete_branch_invalidates(repo: Path, manual_observer: ManualObserver) -> None:
    nixer = FakeNixer()
    git_test_commit()
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    check_call(["git", "checkout", "main"])
    bs = set(branches(nixer))
    assert bs == {Branch("main"), Branch("bug/101")}
    check_call(["git", "branch", "-d", "bug/101"])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    bs = set(branches(FakeNixer()))
    assert bs == {Branch("main")}
