import zlib
from pathlib import Path
from typing import Iterable

from git_graph_branch.git.pack import ObjectKind, Pack, PackData, PackIndex

data_dir = Path(__file__).parent / "data"


def example_pack() -> Pack:
    index = PackIndex(data_dir / "example.idx")
    data = PackData(data_dir / "example.pack")
    return Pack(index, data)


def decompress(compressed: Iterable[bytes]) -> bytes:
    z = zlib.decompressobj(zlib.MAX_WBITS)
    decompressed_chunks: list[bytes] = []
    for compressed_chunk in compressed:
        decompressed_chunks.append(z.decompress(compressed_chunk))
        if z.eof:
            return b"".join(decompressed_chunks)
    raise Exception("File ended unexpectedly")


def test_read_commit() -> None:
    pack = example_pack()
    kind, data = pack["872d4a6538aa4cbbae254b78202dc23eec0ee1b0"]
    assert kind == ObjectKind.COMMIT
    assert data == (
        b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
        b"parent 32bdb01503a97df72e75a5349c61d3106b2b9893\n"
        b"author Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"committer Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"\nCommit 9\n"
    )


def test_read_tree() -> None:
    pack = example_pack()
    kind, data = pack["4b825dc642cb6eb9a060e54bf8d69288fbee4904"]
    assert kind == ObjectKind.TREE
    assert data == b""


def test_read_ofs_deltas() -> None:
    pack = example_pack()
    kind, data = pack["6aa6ed48d0f5a5b3dee398b5fd92ce85a16f9f6b"]
    assert kind == ObjectKind.COMMIT
    assert data == (
        b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
        b"parent 3577e8d8a0037df052e118fbae6d6725ccd1ce93\n"
        b"author Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"committer Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"\nCommit 1\n"
    )
