from pathlib import Path
from subprocess import check_call

from git_graph_branch.git import Commit

from .utils import git_test_commit, git_test_merge


def test_commit_single_line_message(repo: Path) -> None:
    hash = git_test_commit(message="Blank commit")
    main = Commit(hash)

    assert main.message == b"Blank commit\n"


def test_commit_multiline_message(repo: Path) -> None:
    hash = git_test_commit(message="Commit\n\nWith no stuff")
    main = Commit(hash)

    assert main.message == b"Commit\n\nWith no stuff\n"


def test_parents_simple_merge_tree(repo: Path) -> None:
    main_hash = git_test_commit()

    check_call(["git", "checkout", "-b", "foo"])
    foo_hash = git_test_commit("foo.txt")

    check_call(["git", "checkout", "main", "-b", "bar"])
    bar_hash = git_test_commit("bar.txt")

    check_call(["git", "checkout", "foo", "-b", "foobar"])
    foobar_hash = git_test_merge("bar")

    main = Commit(main_hash)
    foo = Commit(foo_hash)
    bar = Commit(bar_hash)
    foobar = Commit(foobar_hash)

    assert main.parents == ()
    assert main.first_parent is None
    assert foo.parents == (main,)
    assert foo.first_parent == main
    assert bar.parents == (main,)
    assert bar.first_parent == main
    assert foobar.parents == (foo, bar)
    assert foobar.first_parent == foo


def test_packed_commits(repo: Path) -> None:
    hashes = []
    for n in range(10):
        hash = git_test_commit(message=f"Commit {n}")
        hashes.append(hash)
    check_call(["git", "gc"])

    for n, hash in enumerate(hashes):
        commit = Commit(hash)
        assert commit.message == f"Commit {n}\n".encode("ascii")
