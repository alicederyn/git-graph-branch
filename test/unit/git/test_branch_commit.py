from pathlib import Path
from subprocess import check_call

import pytest

from git_graph_branch.git import Branch, Commit
from git_graph_branch.ixnay import SingleUseNixer
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver

from .utils import git_test_commit


def test_simple_names(repo: Path) -> None:
    nixer = SingleUseNixer()
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", "feature"])

    assert Branch("main").commit(nixer) == Commit(commit)
    assert Branch("feature").commit(nixer) == Commit(commit)


def test_hash_in_name(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", "foo#bar"])
    assert Branch("foo#bar").commit(SingleUseNixer()) == Commit(commit)


def test_quote_in_name(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", 'foo"bar'])
    assert Branch('foo"bar').commit(SingleUseNixer()) == Commit(commit)


def test_slash_in_name(repo: Path) -> None:
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", "bug/101"])
    assert Branch("bug/101").commit(SingleUseNixer()) == Commit(commit)


@pytest.mark.parametrize("branch_name", ["feature", "foo#bar", 'foo"bar', "bug/101"])
def test_invalidation(
    repo: Path, branch_name: str, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    branch = Branch(branch_name)
    commit = git_test_commit()
    check_call(["git", "checkout", "main", "-b", branch_name])
    assert branch.commit(nixer) == Commit(commit)
    commit2 = git_test_commit()
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    assert branch.commit(FakeNixer()) == Commit(commit2)
