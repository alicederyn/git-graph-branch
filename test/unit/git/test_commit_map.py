from unittest.mock import Mock

import pytest

from git_graph_branch.git.commit_algos import CommitMap


def mock_commit(commit_date: int) -> Mock:
    return Mock(
        commit_date=commit_date,
        hash=f"c{commit_date}",
        name=f"mock_commit({commit_date})",
    )


def test_setitem() -> None:
    c1 = mock_commit(100)
    c2 = mock_commit(101)

    m: CommitMap[str] = CommitMap()
    m[c1] = "a"
    assert m[c1] == "a"
    with pytest.raises(KeyError):
        m[c2]

    m[c2] = "b"
    assert m[c1] == "a"
    assert m[c2] == "b"

    m[c1] = "c"
    assert m[c1] == "c"
    assert m[c2] == "b"


def test_popitem() -> None:
    c1 = mock_commit(100)
    c2 = mock_commit(101)
    c3 = mock_commit(102)
    c4 = mock_commit(103)

    m: CommitMap[str] = CommitMap()
    m[c3] = "c"
    m[c1] = "a"
    m[c4] = "d"
    m[c2] = "b"
    m[c3] = "e"

    assert m.popitem() == (c4, "d")
    assert m.popitem() == (c3, "e")
    assert m.popitem() == (c2, "b")
    assert m.popitem() == (c1, "a")

    with pytest.raises(KeyError):
        m.popitem()

    with pytest.raises(KeyError):
        m[c4]


def test_delitem() -> None:
    c1 = mock_commit(100)
    c2 = mock_commit(101)

    m: CommitMap[str] = CommitMap()
    m[c1] = "a"
    m[c2] = "b"
    del m[c2]

    assert "c2" not in m
    with pytest.raises(KeyError):
        m[c2]
    assert m.popitem() == (c1, "a")
