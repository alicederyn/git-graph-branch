from pathlib import Path
from random import randbytes
from shutil import copy
from subprocess import DEVNULL, check_call

from git_graph_branch.git.pack import PackIndex

from .utils import head_hash

DATA_DIR = Path(__file__).parent / "data"


def example_pack_index() -> PackIndex:
    return PackIndex(DATA_DIR / "example.idx")


def test_contains_hit() -> None:
    with example_pack_index() as index:
        assert "d1b37f4bb24fc3af65a9cf60c9a879897ea4c051" in index


def test_contains_miss() -> None:
    with example_pack_index() as index:
        assert "7161e6dc743b883ccfa513e112e2c7ff16700de3" not in index


def test_getitem_first() -> None:
    # First item in the index
    with example_pack_index() as index:
        assert index["2b4653de60e67022da670d3b05efc4f246b7f3cc"] == 0x101


def test_getitem_middle() -> None:
    # Sixth item in the index
    with example_pack_index() as index:
        assert index["4dde849412579709b3952e4b66e12c1bf5229caf"] == 0x142


def test_getitem_last() -> None:
    # Eleventh item in the index
    with example_pack_index() as index:
        assert index["d1b37f4bb24fc3af65a9cf60c9a879897ea4c051"] == 0x204


def test_getitem_large_offsets() -> None:
    with PackIndex(DATA_DIR / "large.idx") as index:
        assert index["0fcc1d14e06739cc34136b83a05a228f5a7cbdd6"] == 0xC
        assert index["29aef9f41d76fce0c60376613b548901379ccd1d"] == 0x2C0
        assert index["47367aa872ce2a2cea39dab9231cee44a0d9046d"] == 0x1001_54A0
        assert index["0fb0b0931ef42707965bfe4e1f66c9ae29ca60ca"] == 0x1_F026_D8EE


def test_length() -> None:
    with PackIndex(DATA_DIR / "large.idx") as index:
        assert len(index) == 93


def test_iteration() -> None:
    with PackIndex(DATA_DIR / "large.idx") as index:
        hashes = set(hash for hash in index)
    assert len(hashes) == 93
    assert "29aef9f41d76fce0c60376613b548901379ccd1d" in hashes
    assert "0fb0b0931ef42707965bfe4e1f66c9ae29ca60ca" in hashes


def test_misses_do_not_reopen_file(tmp_path: Path) -> None:
    # Copy the test index to a temporary location
    index_copy = tmp_path / "example.index"
    copy(DATA_DIR / "example.idx", index_copy)

    # Warm up the index
    index = PackIndex(index_copy)
    with index:
        assert "460ca587c0f9cffa9d3dc5ed4b8d8dbe16356f80" not in index

    # Trash the index to verify it is not hit again
    index_copy.write_bytes(b"")
    index_copy.unlink()

    # Subsequent miss should not incur the cost of a file read
    with index:
        assert "10c865f91a52f9d5f501874e670b39886ecca717" not in index


def commit_large_file(path: Path, size: int) -> str:
    """Write out uncompressible noise to a file until it reaches a given size and commit it."""
    with open(path, "wb") as f:
        while f.tell() < size:
            f.write(randbytes(0x1000))
    check_call(["git", "add", path], stdout=DEVNULL, stderr=DEVNULL)
    check_call(
        ["git", "commit", "-m", f"Wrote large file {path.name}"],
        stdout=DEVNULL,
        stderr=DEVNULL,
    )
    path.unlink()
    return head_hash()
