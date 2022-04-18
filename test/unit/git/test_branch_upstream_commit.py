from pathlib import Path
from subprocess import check_call, check_output

from git_graph_branch.git import Branch, Commit


def head_commit() -> Commit:
    return Commit(check_output(["git", "rev-parse", "HEAD"], encoding="ascii").strip())


def test_no_upstream(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 1"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 2"])
    b = Branch("main")
    assert b.upstream_commit is None


def test_simple_direct_history(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 1"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 2"])
    expected = head_commit()
    check_call(["git", "checkout", "-tb", "feature"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 3"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 4"])
    b = Branch("feature")
    assert b.upstream_commit == expected


def test_commit_only_in_history(repo: Path) -> None:
    # User works on two features, one extending another
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 1"])
    check_call(["git", "checkout", "-tb", "feature1"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 2"])
    expected = head_commit()
    check_call(["git", "checkout", "-tb", "feature2"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 3"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 4"])

    # User adds an extra commit to first feature and merges it into main
    check_call(["git", "checkout", "feature1"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 5"])
    check_call(["git", "checkout", "main"])
    check_call(["git", "reset", "--hard", "feature1"])
    check_call(["git", "branch", "feature2", "--set-upstream-to", "main"])

    # Common commit is in the upstream's history, but not its reflog
    assert Branch("feature2").upstream_commit == expected


def test_commit_only_in_reflog_history(repo: Path) -> None:
    # User works on two features, one extending another
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 1"])
    check_call(["git", "checkout", "-tb", "feature1"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 2"])
    expected = head_commit()
    check_call(["git", "checkout", "-tb", "feature2"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 3"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 4"])

    # User adds an extra commit to first feature and merges it into main
    check_call(["git", "checkout", "feature1"])
    check_call(["git", "commit", "--allow-empty", "-m", "Commit 5"])
    check_call(["git", "checkout", "main"])
    check_call(["git", "reset", "--hard", "feature1"])
    check_call(["git", "branch", "feature2", "--set-upstream-to", "main"])

    # User rewrites main's history to fix a mistake
    check_call(["git", "checkout", "HEAD^^"])
    check_call(["git", "commit", "--allow-empty", "-m", "Fixed Commit 2"])
    check_call(["git", "commit", "--allow-empty", "-m", "Fixed Commit 5"])
    check_call(["git", "checkout", "-B", "main"])

    # Common commit is only reachable via history of commit in upstream's reflog
    assert Branch("feature2").upstream_commit == expected
