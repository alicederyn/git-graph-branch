from pathlib import Path
from subprocess import check_call

import pytest

from git_graph_branch.git import Branch
from git_graph_branch.ixnay import SingleUseNixer
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver

from .utils import git_test_commit


def test_main_no_upstream(repo: Path) -> None:
    git_test_commit()
    b = Branch("main")
    assert b.upstream(SingleUseNixer()) is None


def test_main_remote_upstream(home_dir: Path, repo: Path) -> None:
    git_test_commit()
    check_call(
        ["git", "remote", "add", "origin", "git@github.com:alicederyn/example.git"]
    )
    check_call(["git", "update-ref", "refs/remotes/origin/main", "main"])
    b = Branch("main")
    assert b.upstream(SingleUseNixer()) is None


def test_upstream_is_main(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "feature"])
    b = Branch("feature")
    assert b.upstream(SingleUseNixer()) == Branch("main")


def test_quote_in_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", 'a"b'])
    check_call(["git", "checkout", "-t", "-b", "feature"])
    b = Branch("feature")
    assert b.upstream(SingleUseNixer()) == Branch('a"b')


def test_hash_in_upstream(repo: Path) -> None:
    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", "a#b"])
    check_call(["git", "checkout", "-t", "-b", "feature"])
    b = Branch("feature")
    assert b.upstream(SingleUseNixer()) == Branch("a#b")


@pytest.mark.parametrize("other_branch", ["foo", "a#b", 'a"b'])
def test_invalidation(
    repo: Path, manual_observer: ManualObserver, other_branch: str
) -> None:
    b = Branch("feature")

    git_test_commit()
    check_call(["git", "checkout", "-t", "-b", other_branch])
    check_call(["git", "checkout", "main", "-t", "-b", "feature"])
    nixer = FakeNixer()
    assert b.upstream(nixer) == Branch("main")

    check_call(["git", "branch", "feature", "--set-upstream-to", other_branch])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    nixer = FakeNixer()
    assert b.upstream(nixer) == Branch(other_branch)

    check_call(["git", "branch", "feature", "--unset-upstream"])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    nixer = FakeNixer()
    assert b.upstream(nixer) is None

    check_call(["git", "branch", "feature", "--set-upstream-to", "main"])
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    assert b.upstream(FakeNixer()) == Branch("main")
