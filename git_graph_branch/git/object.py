import re
from dataclasses import dataclass

TIMESTAMP = re.compile(rb" (\d+)( [+-]\d+)?$")


@dataclass
class GitObject:
    timestamp: int
    parents: tuple[str, ...]
    message: bytes

    @property
    def first_parent(self) -> str | None:
        return self.parents[0] if self.parents else None

    @classmethod
    def decode(cls, data: bytes) -> "GitObject":
        """Parses a git commit object for metadata"""
        parents: list[str] = []
        lines = iter(data[data.find(b"\0") + 1 :].split(b"\n"))
        timestamp: int | None = None
        while line := next(lines):
            if line.startswith(b"parent "):
                parents.append(line.removeprefix(b"parent ").decode("ascii"))
            elif line.startswith(b"author "):
                m = TIMESTAMP.search(line)
                if not m:
                    raise Exception("Possible corruption: unparseable author line")
                timestamp = int(m.group(1))
        if timestamp is None:
            raise Exception("Possible corruption: missing author date")
        message = b"\n".join(lines)
        return cls(timestamp=timestamp, parents=tuple(parents), message=message)
