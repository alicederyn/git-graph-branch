from pathlib import Path
from subprocess import check_call, check_output

from git_graph_branch.git import Branch, Commit


def head_commit() -> Commit:
    return Commit(check_output(["git", "rev-parse", "HEAD"], encoding="ascii").strip())


def test_reflog_reversed(repo: Path) -> None:
    commits = []
    for i in range(10):
        check_call(["git", "commit", "--allow-empty", "-m", f"Commit {i}"])
        commits.append(head_commit())
    check_call(["git", "reset", "--hard", "HEAD^^^"])
    commits.append(commits[-4])
    for i in range(4):
        check_call(["git", "commit", "--allow-empty", "-m", f"Commit {i + 10}"])
        commits.append(head_commit())

    assert commits == list(Branch("main").reflog_reversed())
