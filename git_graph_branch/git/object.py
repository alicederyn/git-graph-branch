from dataclasses import dataclass


@dataclass
class GitObject:
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
        while line := next(lines):
            if line.startswith(b"parent "):
                parents.append(line.removeprefix(b"parent ").decode("ascii"))
        message = b"\n".join(lines)
        return cls(parents=tuple(parents), message=message)
