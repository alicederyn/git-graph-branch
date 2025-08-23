from pathlib import Path

import pytest

from git_graph_branch.git.file_algos import readlines_reversed


def write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def write_bytes(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    "payload,chunk_size",
    [
        pytest.param("", 1024, id="empty-file"),
        pytest.param("alpha", 1024, id="single-line-no-trailing-newline"),
        pytest.param("alpha\n", 1024, id="single-line-with-trailing-newline"),
        pytest.param("a\nb\nc", 1024, id="multiple-lines-no-trailing-newline"),
        pytest.param("a\nb\nc\n", 1024, id="multiple-lines-with-trailing-newline"),
        pytest.param("a\nb\nc\n\n", 1024, id="multiple-trailing-newlines"),
        pytest.param(b"a\r\nb\r\nc\r\n", 1024, id="crlf"),
        *[
            pytest.param("x" * 5000, cs, id=f"long-line-chunk-size-chunk={cs}")
            for cs in [1, 2, 3, 4, 8, 64, 1024]
        ],
        pytest.param(
            "a" * 1023 + "\n" + "b", 1024, id="newline-exactly-on-chunk-boundary"
        ),
        pytest.param(
            "alpha\n" + ("b" * 1500) + "\n" + "gamma", 1024, id="line-spans-chunks"
        ),
        pytest.param(("a" * 1024) + "\n\nb", 1024, id="chunk-begins-with-newline"),
        *[
            pytest.param(
                "😀\nñandú\n最后一行", cs, id=f"unicode-across-small-chunks-chunk={cs}"
            )
            for cs in [1, 2, 3, 4, 8, 16]
        ],
        *[
            pytest.param(
                "a" * 3000,
                cs,
                id=f"large-no-newline-across-chunks-chunk={cs}",
            )
            for cs in [1000, 1024]
        ],
        pytest.param("a\nb\n\n\n", 2, id="three-trailing-newlines-drop-one-keepends"),
        pytest.param(b"a\r\nb\r\nc", 1, id="crlf-split-across-chunk-boundary"),
    ],
)
def test_matches_naive_implementation(
    tmp_path: Path, payload: bytes | str, chunk_size: int
) -> None:
    path = tmp_path / "f.txt"
    if isinstance(payload, str):
        write_text(path, payload)
    else:
        write_bytes(path, payload)
    expected = list(reversed(list(path.open("r", encoding="utf-8"))))

    result = list(readlines_reversed(path, chunk_size=chunk_size))

    assert result == expected


def test_invalid_utf8_raises(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    write_bytes(path, b"ok\n\xff\xfe")
    with pytest.raises(UnicodeDecodeError):
        list(readlines_reversed(path))
