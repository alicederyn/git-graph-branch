from pathlib import Path
from subprocess import check_call, check_output

from .utils import git_test_commit, git_test_merge


def test_main_merged_into_feature_branch(repo: Path) -> None:
    """
      ┬  F -- Head of feature branch
    ┬ │  C -- Head of main branch
    ├▶┤  E
    ┼ │  B
    ├▶┘  D
    ┴  A
    """
    commit_a = git_test_commit("main.txt")
    commit_b = git_test_commit("main.txt")
    git_test_commit("main.txt")

    check_call(["git", "checkout", commit_a, "-qb", "feature"])
    check_call(["git", "branch", "-q", "--set-upstream-to", "main"])
    git_test_commit("branch.txt")
    git_test_merge(commit_b)
    git_test_commit("branch.txt")

    # Current status according to git:
    status = check_output(["git", "status"], encoding="ascii")
    assert "Your branch and 'main' have diverged" in status
    assert "3 and 1 different commits each" in status


def test_upstream_branch_rebased(repo: Path) -> None:
    """
    ┬ D -- Head of main branch
    │ ┬  C  -- Head of feature branch
    ├▶┘  B  -- On reflog of main branch
    ┴  A
    """
    git_test_commit("main.txt")
    commit_b = git_test_commit("main.txt")
    git_test_commit("README.md", amend=True)

    check_call(["git", "checkout", commit_b, "-qb", "feature"])
    check_call(["git", "branch", "-q", "--set-upstream-to", "main"])
    commit_d = git_test_commit("branch.txt")

    # Current status according to git:
    status = check_output(["git", "status"], encoding="ascii")
    assert "Your branch and 'main' have diverged" in status
    assert "2 and 1 different commits each" in status

    # git rebase respects the reflog, however:
    check_call(["git", "rebase", "-q"])
    status = check_output(["git", "status"], encoding="ascii")
    assert "Your branch is ahead of 'main' by 1 commit" in status

    # Restore the test setup
    check_call(["git", "reset", "--hard", "-q", commit_d])
