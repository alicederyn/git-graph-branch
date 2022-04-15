from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Type


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
