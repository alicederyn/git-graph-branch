import zlib
from io import BytesIO
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


def decode_copy(instr: int, f: BinaryIO, base: bytes) -> bytes:
    """Decodes a copy instruction from a git delta

    See also https://git-scm.com/docs/pack-format#_instruction_to_copy_from_base_object
    """
    offset = 0
    size = 0
    try:
        if instr & 0x1:
            offset |= f.read(1)[0]
        if instr & 0x2:
            offset |= f.read(1)[0] << 8
        if instr & 0x4:
            offset |= f.read(1)[0] << 16
        if instr & 0x8:
            offset |= f.read(1)[0] << 24
        if instr & 0x10:
            size |= f.read(1)[0]
        if instr & 0x20:
            size |= f.read(1)[0] << 8
        if instr & 0x40:
            size |= f.read(1)[0] << 16
    except IndexError:
        raise Exception("Unexpected end of file")
    if size == 0:
        size = 0x10000
    if offset + size > len(base):
        raise Exception("Possible corruption: copy instruction too large")
    return base[offset : offset + size]


def apply_delta(base: bytes, delta: bytes) -> bytes:
    """Applies a git delta

    See also https://git-scm.com/docs/pack-format#_deltified_representation
    """
    # The delta data starts with the size of the base object and the size of the
    # object to be reconstructed. These sizes are encoded using...size encoding
    f = BytesIO(delta)
    base_size = read_size(f)
    if len(base) != base_size:
        raise Exception("Possible corruption: size mismatch")
    length = read_size(f)

    chunks = []
    while instr := f.read(1):
        if instr[0] & 0x80:
            # Instruction to copy from base object
            chunks.append(decode_copy(instr[0], f, base))
        elif instr[0] == 0:
            # Reserved for future encoding extensions
            raise Exception("Unexpected delta opcode 0")
        else:
            # Raw data
            chunks.append(f.read(instr[0]))
    result = b"".join(chunks)
    if len(result) != length:
        raise Exception("Possible corruption: size mismatch")
    return result
