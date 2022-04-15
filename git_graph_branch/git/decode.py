import zlib
from typing import Iterable


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
