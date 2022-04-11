import zlib
from dataclasses import dataclass
from typing import Iterable


def decompress(commit: Iterable[bytes]) -> bytes:
    z = zlib.decompressobj(zlib.MAX_WBITS)
    decompressed: list[bytes] = []
    for compressed in commit:
        decompressed.append(z.decompress(compressed))
    decompressed.append(z.flush())
    return b"".join(decompressed)


@dataclass
class GitObject:
    parents: tuple[str, ...]
    message: bytes

    @property
    def first_parent(self) -> str | None:
        return self.parents[0] if self.parents else None

    @classmethod
    def decode(cls, commit: Iterable[bytes]) -> "GitObject":
        """Parses a git commit object for metadata"""
        raw = decompress(commit)
        parents: list[str] = []
        lines = iter(raw[raw.find(b"\0") + 1 :].split(b"\n"))
        while line := next(lines):
            if line.startswith(b"parent "):
                parents.append(line.removeprefix(b"parent ").decode("ascii"))
        message = b"\n".join(lines)
        return cls(parents=tuple(parents), message=message)
