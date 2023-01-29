import re
from dataclasses import dataclass

TIMESTAMP = re.compile(rb" (\d+)( [+-]\d+)?$")


@dataclass
class GitObject:
    commit_date: int
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
        commit_date: int | None = None
        timestamp: int | None = None
        while line := next(lines):
            if line.startswith(b"parent "):
                parents.append(line.removeprefix(b"parent ").decode("ascii"))
            elif line.startswith(b"author "):
                m = TIMESTAMP.search(line)
                if not m:
                    raise Exception("Possible corruption: unparseable author line")
                timestamp = int(m.group(1))
            elif line.startswith(b"committer "):
                m = TIMESTAMP.search(line)
                if not m:
                    raise Exception("Possible corruption: unparseable committer line")
                commit_date = int(m.group(1))
        if timestamp is None:
            raise Exception("Possible corruption: missing author date")
        if commit_date is None:
            raise Exception("Possible corruption: missing commit date")
        message = b"\n".join(lines)
        return cls(
            commit_date=commit_date,
            timestamp=timestamp,
            parents=tuple(parents),
            message=message,
        )
