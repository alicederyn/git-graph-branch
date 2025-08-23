from typing import Callable

from git_graph_branch.git.file_algos import CloseablesCache


class FakeCloseable:
    def __init__(self, id: int, callback: "Callable[[FakeCloseable], None]") -> None:
        self._id = id
        self._callback = callback

    def close(self) -> None:
        self._callback(self)

    def __repr__(self) -> str:
        return f"FakeCloseable({self._id})"

    def __hash__(self) -> int:
        return self._id

    def __eq__(self, value: object, /) -> bool:
        return isinstance(value, FakeCloseable) and value._id == self._id


class FakeCloseables:
    def __init__(self) -> None:
        self.closed: set[FakeCloseable] = set()
        self._last_id: int = 0

    def create(self) -> FakeCloseable:
        self._last_id += 1
        return FakeCloseable(self._last_id, self.closed.add)


def test_least_recently_added_is_closed() -> None:
    closeables = FakeCloseables()
    c1 = closeables.create()
    c2 = closeables.create()
    c3 = closeables.create()
    c4 = closeables.create()
    c5 = closeables.create()
    c6 = closeables.create()

    cache = CloseablesCache(max_size=5)
    cache.add(c1)
    cache.add(c2)
    cache.add(c3)
    cache.add(c4)
    cache.add(c5)
    cache.add(c2)
    cache.add(c4)
    cache.add(c1)
    assert not closeables.closed

    cache.add(c6)
    assert closeables.closed == {c3}

    cache.add(c2)
    assert closeables.closed == {c3}

    cache.add(c3)
    assert closeables.closed == {c3, c5}

    cache.add(c5)
    assert closeables.closed == {c3, c4, c5}
