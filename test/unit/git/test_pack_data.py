import zlib
from pathlib import Path
from typing import Iterable

from git_graph_branch.git.pack import DataObject, Delta, ObjectKind, PackData

data_dir = Path(__file__).parent / "data"


def example_pack() -> PackData:
    return PackData(data_dir / "example.pack")


def decompress(compressed: Iterable[bytes]) -> bytes:
    z = zlib.decompressobj(zlib.MAX_WBITS)
    decompressed_chunks: list[bytes] = []
    for compressed_chunk in compressed:
        decompressed_chunks.append(z.decompress(compressed_chunk))
        if z.eof:
            return b"".join(decompressed_chunks)
    raise Exception("File ended unexpectedly")


def test_read_commit() -> None:
    with example_pack() as pack:
        obj = pack.read_object(0x00C)
        assert isinstance(obj, DataObject)
        assert obj.kind == ObjectKind.COMMIT
        assert obj.length == 251
        data = decompress(obj.compressed_data)
        assert data.startswith(b"tree 4b825dc642")
        assert len(data) == obj.length


def test_read_tree() -> None:
    with example_pack() as pack:
        obj = pack.read_object(0x2C7)
        assert isinstance(obj, DataObject)
        assert obj.kind == ObjectKind.TREE
        assert obj.length == 0
        data = decompress(obj.compressed_data)
        assert data == b""


def test_read_ofs_deltas() -> None:
    with example_pack() as pack:
        delta = pack.read_object(0x0C3)
        assert isinstance(delta, Delta)
        assert delta.relative_to == (0x00C)
        instructions = decompress(delta.compressed_instructions)
        assert instructions.hex() == (
            "fb01fb0190362535373765386438613030333764663035326531313866626165"
            "366436373235636364316365915b9e02310a"
        )
        assert delta.length == len(instructions)
