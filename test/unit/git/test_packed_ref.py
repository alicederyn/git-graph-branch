from pathlib import Path

from git_graph_branch.git.branch import RemoteBranch
from git_graph_branch.git.commit import Commit


def test_packed_remote_branch(repo: Path, worktree: Path) -> None:
    (repo / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        "1234567890abcdef refs/remotes/origin/main\n"
    )

    branch = RemoteBranch("origin", "main")

    assert branch.commit == Commit("1234567890abcdef")
