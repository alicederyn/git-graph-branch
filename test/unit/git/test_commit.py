from pathlib import Path
from subprocess import check_call, check_output

from git_graph_branch.git import Commit


def touch(filename: str) -> None:
    with open(filename, "w"):
        pass


def head_hash() -> str:
    return check_output(["git", "rev-parse", "HEAD"], encoding="ascii").strip()


def test_commit_single_line_message(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Blank commit"])
    main = Commit(head_hash())

    assert main.message == b"Blank commit\n"


def test_commit_multiline_message(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Commit\n\nWith no stuff"])
    main = Commit(head_hash())

    assert main.message == b"Commit\n\nWith no stuff\n"


def test_parents_simple_merge_tree(repo: Path) -> None:
    check_call(["git", "commit", "--allow-empty", "-m", "Blank commit"])
    main_hash = head_hash()

    check_call(["git", "checkout", "-b", "foo"])
    touch("foo.txt")
    check_call(["git", "add", "foo.txt"])
    check_call(["git", "commit", "-m", "Add foo.txt"])
    foo_hash = head_hash()

    check_call(["git", "checkout", "main", "-b", "bar"])
    touch("bar.txt")
    check_call(["git", "add", "bar.txt"])
    check_call(["git", "commit", "bar.txt", "-m", "Add bar.txt"])
    bar_hash = head_hash()

    check_call(["git", "checkout", "foo", "-b", "foobar"])
    check_call(["git", "merge", "bar"])
    foobar_hash = head_hash()

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
        check_call(["git", "commit", "--allow-empty", "-m", f"Commit {n}"])
        hashes.append(head_hash())
    check_call(["git", "gc"])

    for n, hash in enumerate(hashes):
        commit = Commit(hash)
        assert commit.message == f"Commit {n}\n".encode("ascii")
