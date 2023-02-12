from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, Commit
from git_graph_branch.ixnay import SingleUseNixer
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver

from .utils import git_test_commit


def test_reflog_reversed(repo: Path) -> None:
    commits = []
    for i in range(10):
        hash = git_test_commit(message=f"Commit {i}")
        commits.append(Commit(hash))
    check_call(["git", "reset", "--hard", "HEAD^^^"])
    commits.append(commits[-4])
    for i in range(4):
        hash = git_test_commit(message=f"Commit {i + 10}")
        commits.append(Commit(hash))

    assert commits == list(Branch("main").reflog_reversed(SingleUseNixer()))


def test_branch_change_invalidates(repo: Path, manual_observer: ManualObserver) -> None:
    nixer = FakeNixer()
    branch = Branch("main")
    git_test_commit()
    result = list(branch.reflog_reversed(nixer))
    assert len(result) == 1
    git_test_commit()
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    result = list(branch.reflog_reversed(FakeNixer()))
    assert len(result) == 2
