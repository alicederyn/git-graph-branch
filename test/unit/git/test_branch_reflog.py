from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, Commit

from .utils import git_test_commit


def test_reflog_commits(repo: Path) -> None:
    expected = []
    for i in range(10):
        hash = git_test_commit(message=f"Commit {i}")
        expected.append(Commit(hash))
    check_call(["git", "reset", "--hard", "HEAD^^^"])
    expected.append(expected[-4])
    for i in range(4):
        hash = git_test_commit(message=f"Commit {i + 10}")
        expected.append(Commit(hash))
    expected.reverse()

    actual = [r.commit for r in Branch("main").reflog()]

    assert actual == expected
