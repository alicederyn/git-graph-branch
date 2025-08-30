from typing import Iterator
from unittest.mock import Mock

from git_graph_branch.git.commit import Commit
from git_graph_branch.git.commit_algos import merge_reverse_chronological


def mock_commit(commit_date: int) -> Mock:
    return Mock(
        commit_date=commit_date,
        hash=f"c{commit_date}",
        name=f"mock_commit({commit_date})",
    )


def test_accepts_empty_iterables() -> None:
    result: list[tuple[Commit, str]] = list(merge_reverse_chronological([[], []]))

    assert result == []


def test_preserves_order() -> None:
    c1 = mock_commit(100)
    c2 = mock_commit(101)
    c3 = mock_commit(102)
    c4 = mock_commit(103)
    c5 = mock_commit(104)
    c6 = mock_commit(105)
    a = [(c6, "a1"), (c3, "a2"), (c1, "a3")]
    b = [(c5, "b1"), (c4, "b2"), (c2, "b3")]

    result = list(merge_reverse_chronological([a, b]))

    assert result == [
        (c6, "a1"),
        (c5, "b1"),
        (c4, "b2"),
        (c3, "a2"),
        (c2, "b3"),
        (c1, "a3"),
    ]


def consume_from[T](items: list[T]) -> Iterator[T]:
    try:
        while True:
            yield items.pop()
    except IndexError:
        pass


def test_consumes_lazily() -> None:
    a: list[tuple[Commit, str]] = [(mock_commit(99), "a1")]
    b: list[tuple[Commit, str]] = [(mock_commit(96), "b1")]
    c: list[tuple[Commit, str]] = [(mock_commit(93), "c1")]

    it = merge_reverse_chronological(
        [consume_from(a), consume_from(b), consume_from(c)]
    )

    assert next(it)[1] == "a1"
    a.append((mock_commit(98), "a2"))
    assert next(it)[1] == "a2"
    a.append((mock_commit(95), "a3"))
    assert next(it)[1] == "b1"
    b.append((mock_commit(90), "b2"))
    assert next(it)[1] == "a3"
    assert next(it)[1] == "c1"
    assert next(it)[1] == "b2"

    assert next(it, None) is None
