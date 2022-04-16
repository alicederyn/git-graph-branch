from math import ceil
from typing import Iterable


class Bloom:
    """A simple in-memory bloom filter to store git hashes

    Gives a 0.1% false positive rate at a cost of 14.4 bits per item.
    """

    _BIT_MASK = {i: 1 << i for i in range(8)}
    _HASHES = 10

    def __init__(self, size: int):
        num_bytes = ceil(1.44 * size * self._HASHES / 8)
        self._data = bytearray(num_bytes)

    @staticmethod
    def _assert_type(key: bytes) -> None:
        if not isinstance(key, bytes):
            raise TypeError("unsupported key type for Bloom filter: " + type(key))

    def _indices(self, key: bytes) -> Iterable[tuple[int, int]]:
        bits = 8 * len(self._data)
        keyint = int.from_bytes(key, byteorder="big")
        for _ in range(self._HASHES):
            keyint, bit = divmod(keyint, bits)
            yield (bit >> 3, self._BIT_MASK[bit & 7])

    def __contains__(self, key: bytes) -> bool:
        self._assert_type(key)
        return all(self._data[idx] & mask for (idx, mask) in self._indices(key))

    def add(self, key: bytes) -> None:
        self._assert_type(key)
        for idx, mask in self._indices(key):
            self._data[idx] |= mask
