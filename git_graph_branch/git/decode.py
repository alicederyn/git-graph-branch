import zlib
from typing import BinaryIO, Iterable


def decompress(commit: Iterable[bytes]) -> bytes:
    """Decompress a stream of bytes

    Note: does not necessarily leave an underlying file object
    at the end of the compressed data at the end; may overshoot
    """
    z = zlib.decompressobj(zlib.MAX_WBITS)
    decompressed: list[bytes] = []
    for compressed in commit:
        decompressed.append(z.decompress(compressed))
        if z.eof:
            return b"".join(decompressed)
    raise Exception("File ended unexpectedly")


def read_size(f: BinaryIO) -> int:
    """Reads a size-encoded non-negative integer

    See also https://git-scm.com/docs/pack-format#_size_encoding
    """
    result = 0
    shift = 0
    while d := f.read(1):
        result |= (d[0] & 0x7F) << shift
        if not (d[0] & 0x80):
            return result
        shift += 7
    raise Exception("Unexpected end of file")


def read_offset(f: BinaryIO) -> int:
    """Reads an offset-encoded non-negative integer

    See also https://git-scm.com/docs/pack-format
    """
    # n bytes with MSB set in all but the last one.
    # The offset is then the number constructed by
    # concatenating the lower 7 bit of each byte, and
    # for n >= 2 adding 2^7 + 2^14 + ... + 2^(7*(n-1))
    # to the result.
    result = -1
    while d := f.read(1):
        result = (result + 1) << 7
        result |= d[0] & 0x7F
        if not (d[0] & 0x80):
            return result
    raise Exception("Unexpected end of file")
