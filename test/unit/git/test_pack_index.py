from pathlib import Path

from git_graph_branch.git.pack import PackIndex

data_dir = Path(__file__).parent / "data"


def example_pack_index() -> PackIndex:
    return PackIndex(data_dir / "example.idx")


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
