import os
from pathlib import Path
from subprocess import check_call
from time import sleep

from git_graph_branch.git.pack import packs

from .utils import git_test_commit


def test_packs_sorted_reverse_chronologically(repo: Path) -> None:
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])
    sleep(0.01)
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])
    sleep(0.01)
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])

    ps = packs()

    mtime0, mtime1, mtime2 = (p._data._path.lstat().st_mtime for p in ps._packs)

    assert mtime0 > mtime1 > mtime2


def test_packs_with_identical_mtimes(repo: Path) -> None:
    # See https://github.com/alicederyn/git-graph-branch/issues/7
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])
    git_test_commit()
    git_test_commit()
    check_call(["git", "repack"])

    # Force all pack objects to have the same mtime.
    pack1, pack2, pack3 = Path(".git", "objects", "pack").glob("*.pack")
    stat = pack1.lstat()
    times = (stat.st_atime, stat.st_mtime)
    os.utime(pack2, times)
    os.utime(pack3, times)

    ps = packs()

    mtime0, mtime1, mtime2 = (p._data._path.lstat().st_mtime for p in ps._packs)

    assert mtime0 == mtime1 == mtime2
