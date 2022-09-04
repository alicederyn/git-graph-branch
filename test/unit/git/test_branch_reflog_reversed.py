from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Branch, Commit

from .utils import head_hash


def test_reflog_reversed(repo: Path) -> None:
    commits = []
    for i in range(10):
        check_call(["git", "commit", "--allow-empty", "-m", f"Commit {i}"])
        commits.append(Commit(head_hash()))
    check_call(["git", "reset", "--hard", "HEAD^^^"])
    commits.append(commits[-4])
    for i in range(4):
        check_call(["git", "commit", "--allow-empty", "-m", f"Commit {i + 10}"])
        commits.append(Commit(head_hash()))

    assert commits == list(Branch("main").reflog_reversed())
