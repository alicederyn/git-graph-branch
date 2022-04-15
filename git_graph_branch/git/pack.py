from enum import Enum
from functools import cache
from io import BufferedIOBase, BufferedReader
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Iterable, Type

from .decode import apply_delta, decompress, read_offset, read_size
from .path import git_dir


class PackIndex:
    def __init__(self, path: Path):
        self._path = path
        self._cache: dict[str, int] = {}
        self._f: BinaryIO | None = None
        self._inited = False
        self._in_with_block = False

    def __enter__(self) -> "PackIndex":
        assert not self._in_with_block
        self._in_with_block = True
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        assert self._in_with_block
        self._in_with_block = False
        if self._f:
            self._f.close()
            self._f = None

    def _open(self) -> BinaryIO:
        assert self._in_with_block
        if not self._f:
            self._f = open(self._path, "rb")
        if not self._inited:
            header = self._f.read(8)
            if header != b"\xfftOc\x00\x00\x00\x02":
                raise Exception("Unsupported pack index format (must be v2)")
            self._f.seek(0x404)
            size = int.from_bytes(self._f.read(4), byteorder="big", signed=False)
            self._small_offsets_table = 0x408 + 24 * size
            self._large_offsets_table = 0x408 + 28 * size
            self._inited = True
        return self._f

    def _find_index(self, hash: bytes) -> int:
        assert self._f

        # Find the stretch of hashes to search
        self._f.seek(4 + 4 * hash[0])
        start = int.from_bytes(self._f.read(4), byteorder="big", signed=False)
        end = int.from_bytes(self._f.read(4), byteorder="big", signed=False)
        if hash[0] == 0:
            # We read the version field; start is always 0 here
            start = 0

        # Binary search for the bytes we want
        while start < end:
            mid = (start + end) // 2
            self._f.seek(0x408 + 20 * mid)
            hash_at_mid = self._f.read(20)
            assert len(hash_at_mid) == 20
            if hash == hash_at_mid:
                return mid
            elif hash < hash_at_mid:
                end = mid
            else:
                start = mid + 1

        raise KeyError(bytes.hex(hash))

    def __getitem__(self, hash: str) -> int:
        if not (isinstance(hash, str)):
            raise TypeError("Pack keys must be str")
        if hash not in self._cache:
            f = self._open()
            idx = self._find_index(bytes.fromhex(hash))
            f.seek(self._small_offsets_table + idx * 4)
            short_bytes = f.read(4)
            short_size = int.from_bytes(short_bytes, byteorder="big", signed=False)
            if short_size < 0x8000:
                size = short_size
            else:
                f.seek(self._large_offsets_table + 8 * (size - 0x8000))
                long_bytes = f.read(8)
                size = int.from_bytes(long_bytes, byteorder="big", signed=False)
            self._cache[hash] = size
        return self._cache[hash]

    def __contains__(self, hash: str) -> bool:
        try:
            self.__getitem__(hash)
            return True
        except KeyError:
            return False


class ObjectKind(Enum):
    COMMIT = 1
    TREE = 2
    BLOB = 3
    TAG = 4


KINDS_BY_VAL: dict[int, ObjectKind] = {t.value: t for t in ObjectKind}
OFS_DELTA = 6
REF_DELTA = 7


class DataObject:
    def __init__(self, kind: ObjectKind, f: BufferedReader, offset: int, length: int):
        self.kind = kind
        self._f = f
        self._offset = offset
        self.length = length

    @property
    def compressed_data(self) -> Iterable[bytes]:
        if self._f.tell() != self._offset:
            self._f.seek(self._offset)
        yield from self._f
        assert not self._f.closed


class Delta:
    def __init__(
        self,
        relative_to: int | str,
        f: BufferedIOBase,
        offset: int,
        length: int,
    ):
        self.relative_to = relative_to
        self._f = f
        self._offset = offset
        self.length = length

    @property
    def compressed_instructions(self) -> Iterable[bytes]:
        if self._f.tell() != self._offset:
            self._f.seek(self._offset)
        for b in self._f:
            yield b


class PackData:
    def __init__(self, path: Path):
        self._path = path
        self._f: BufferedReader | None = None
        self._inited = False
        self._in_with_block = False

    def __enter__(self) -> "PackData":
        assert not self._in_with_block
        assert not self._f
        self._in_with_block = True
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        assert self._in_with_block
        self._in_with_block = False
        if f := self._f:
            self._f = None
            f.close()

    def _open(self) -> None:
        assert self._in_with_block
        if not self._f:
            f = open(self._path, "rb")
            assert isinstance(f, BufferedReader)
            self._f = f
        if not self._inited:
            header = self._f.read(8)
            if header != b"PACK\x00\x00\x00\x02":
                raise Exception("Unsupported pack format (must be v2)")
            self._inited = True

    def read_object(self, offset: int) -> DataObject | Delta:
        if offset < 12:
            raise Exception("Possible corruption: invalid offset")
        self._open()
        assert self._f
        self._f.seek(offset)
        size = read_size(self._f)
        kind_bits = (size >> 4) & 0x7
        size = (size & 0xF) | ((size >> 7) << 4)
        kind = KINDS_BY_VAL.get(kind_bits)
        if kind is not None:
            return DataObject(kind, self._f, self._f.tell(), size)
        relative_to: int | str
        if kind_bits == OFS_DELTA:
            relative_to = offset - read_offset(self._f)
        elif kind_bits == REF_DELTA:
            relative_to = self._f.read(20).hex()
        else:
            raise Exception(f"Unexpected object type ({kind_bits})")
        return Delta(relative_to, self._f, self._f.tell(), size)


class Pack:
    def __init__(self, index: PackIndex, data: PackData):
        self._index = index
        self._data = data

    def _object_at_offset(self, offset: int) -> tuple[ObjectKind, bytes]:
        obj = self._data.read_object(offset)
        if isinstance(obj, DataObject):
            kind = obj.kind
            data = decompress(obj.compressed_data)
            if len(data) != obj.length:
                raise Exception("Possible corruption: size mismatch")
        else:
            assert self._data._f and not self._data._f.closed
            assert not obj._f.closed
            instructions = decompress(obj.compressed_instructions)
            assert not obj._f.closed
            assert self._data._f and not self._data._f.closed
            if len(instructions) != obj.length:
                raise Exception("Possible corruption: size mismatch")
            base_ref = obj.relative_to
            if isinstance(base_ref, int):
                kind, base = self._object_at_offset(base_ref)
            else:
                try:
                    kind, base = self._object_at_offset(self._index[base_ref])
                except KeyError:
                    raise Exception("Possible corruption: missing base ref")
            data = apply_delta(base, instructions)
        return (kind, data)

    def __getitem__(self, hash: str) -> tuple[ObjectKind, bytes]:
        with self._index:
            offset = self._index[hash]
            with self._data:
                return self._object_at_offset(offset)

    def __contains__(self, hash: str) -> bool:
        with self._index:
            return hash in self._index


class PackDir:
    def __init__(self, pack_dir: Path):
        assert pack_dir.is_dir()
        packs: list[tuple[float, Pack]] = []
        for data_file in pack_dir.glob("*.pack"):
            data = PackData(data_file)
            index_file = data_file.with_suffix(".idx")
            if not index_file.is_file:
                raise Exception("Missing index for pack file " + data_file)
            index = PackIndex(index_file)
            mtime = data_file.stat().st_mtime
            packs.append((mtime, Pack(index, data)))
        packs.sort(reverse=True)
        self._packs = tuple(p[1] for p in packs)

    def __getitem__(self, hash: str) -> tuple[ObjectKind, bytes]:
        if not (isinstance(hash, str)):
            raise TypeError("Pack keys must be str")
        for pack in self._packs:
            try:
                return pack[hash]
            except KeyError:
                pass
        raise KeyError(hash)

    def __contains__(self, hash: str) -> bool:
        return any(hash in pack for pack in self._packs)


@cache
def packs() -> PackDir:
    return PackDir(git_dir() / "objects" / "pack")
