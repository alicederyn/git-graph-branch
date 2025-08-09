import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from git_graph_branch.git.branch import RemoteBranch
from git_graph_branch.git.commit import Commit


@pytest.fixture(autouse=True)
def repo(tmp_path: Path) -> Iterator[Path]:
    wd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    yield tmp_path

    os.chdir(wd)


def test_packed_remote_branch(repo: Path) -> None:
    (repo / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        "1234567890abcdef refs/remotes/origin/main\n"
    )

    branch = RemoteBranch("origin", "main")

    assert branch.commit == Commit("1234567890abcdef")
