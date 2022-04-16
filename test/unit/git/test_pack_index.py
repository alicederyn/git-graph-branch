from pathlib import Path
from shutil import copy

from git_graph_branch.git.pack import PackIndex

index_path = Path(__file__).parent / "data" / "example.idx"


def example_pack_index() -> PackIndex:
    return PackIndex(index_path)


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


def test_misses_do_not_reopen_file(tmp_path: Path) -> None:
    # Copy the test index to a temporary location
    index_copy = tmp_path / "example.index"
    copy(index_path, index_copy)

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
