from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, Commit

from .utils import git_test_commit


def test_reflog(repo: Path) -> None:
    commits = []
    for i in range(10):
        hash = git_test_commit(message=f"Commit {i}")
        commits.append(Commit(hash))
    check_call(["git", "reset", "--hard", "HEAD^^^"])
    commits.append(commits[-4])
    for i in range(4):
        hash = git_test_commit(message=f"Commit {i + 10}")
        commits.append(Commit(hash))

    assert list(reversed(commits)) == list(Branch("main").reflog())
