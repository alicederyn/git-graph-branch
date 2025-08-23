import os
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

from git_graph_branch.git.file_algos import PooledBinaryReader, handle_cache


@pytest.fixture(autouse=True)
def allow_only_two_handles() -> Iterator[None]:
    with patch.object(handle_cache(), "max_size", 2):
        yield


def test_transparent_close_and_reopen(tmp_path: Path) -> None:
    p1 = tmp_path / "a.txt"
    p1.write_bytes(b"abcdefgh")
    p2 = tmp_path / "b.txt"
    p2.write_bytes(b"ijklmnop")
    p3 = tmp_path / "c.txt"
    p3.write_bytes(b"qrstuvwx")

    with (
        PooledBinaryReader(p1) as f1,
        PooledBinaryReader(p2) as f2,
        PooledBinaryReader(p3) as f3,
    ):
        assert f1.read(4) == b"abcd"
        assert f2.read(4) == b"ijkl"
        assert f3.read(4) == b"qrst"
        assert f1.read(4) == b"efgh"
        assert f1.seek(0) == 0
        assert f2.read(4) == b"mnop"
        assert f3.seek(-2, os.SEEK_CUR) == 2
        assert f3.read(4) == b"stuv"
        assert f1.read(4) == b"abcd"
