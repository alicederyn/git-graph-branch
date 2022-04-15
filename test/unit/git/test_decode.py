from io import BytesIO
from pathlib import Path

from git_graph_branch.git.decode import apply_delta, decompress

data_dir = Path(__file__).parent / "data"


def test_decompress() -> None:
    # Compressed object taken from offset 0x00C in example.pack
    COMPRESSED = bytes.fromhex(
        "789cadcc4b0ac2301000d07d4e317b5126bf490644046f207a804c3345c15689"
        "29787c8b6770fb16af375508925dac03053708a97041428d41c65c895dcea3a8"
        "06c6605ea5e9dcc13ba98236a22f9cea989ca658a20f3c90adde228913ceec4d"
        "59faedd9e03adf3b5cf4dde1bcccb336d82fab6cfb2adbf693a37ecaf47ae86e"
        "784e07b01498528a84b0418b68569deebdeb1f2a73fa5dc0e60bc91b4d6c"
    )

    result = decompress(BytesIO(COMPRESSED))
    assert result == (
        b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
        b"parent 32bdb01503a97df72e75a5349c61d3106b2b9893\n"
        b"author Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"committer Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"\nCommit 9\n"
    )


def test_apply_delta() -> None:
    # Base object taken from offset 0x00C in example.pack
    BASE = (
        b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
        b"parent 32bdb01503a97df72e75a5349c61d3106b2b9893\n"
        b"author Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"committer Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"\nCommit 9\n"
    )
    # Delta object taken from offset 0x0C3 in example.pack
    DELTA = bytes.fromhex(
        "fb01fb0190362535373765386438613030333764663035326531313866626165"
        "366436373235636364316365915b9e02310a"
    )

    result = apply_delta(BASE, DELTA)
    assert result == (
        b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
        b"parent 3577e8d8a0037df052e118fbae6d6725ccd1ce93\n"
        b"author Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"committer Unit Test Runner <unit-test-runner@example.com> 1649677560 +0100\n"
        b"\nCommit 1\n"
    )
