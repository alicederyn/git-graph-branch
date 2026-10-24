import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from git_graph_branch.nix.files import Glob, GlobState, PathState

CONFIG = Path("./.gitconfig")
PACK_DIR = Path("./.git/objects/pack")
PACK1 = PACK_DIR / "1.pack"
PACK2 = PACK_DIR / "2.pack"


def touch(path: Path, at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    os.utime(path, (at.timestamp(), at.timestamp()))


@pytest.fixture
def last_check(tmp_path: Path) -> Iterator[datetime]:
    value = datetime.now(UTC) - timedelta(seconds=2)

    orig_wd = os.getcwd()
    os.chdir(tmp_path)

    # Create some files, with modification timestamp
    # a minute before the last check
    for path in (CONFIG, PACK1, PACK2):
        touch(path, value - timedelta(minutes=1))

    yield value

    os.chdir(orig_wd)


def test_single_file_not_modified(last_check: datetime) -> None:
    state = PathState(CONFIG, existed=True, timestamp=last_check.timestamp())

    result = state.should_nix()

    assert not result


def test_single_file_created(last_check: datetime) -> None:
    state = PathState(CONFIG, existed=False, timestamp=last_check.timestamp())
    touch(CONFIG, last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert result


def test_single_file_modified(last_check: datetime) -> None:
    state = PathState(CONFIG, existed=True, timestamp=last_check.timestamp())
    touch(CONFIG, last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert result


def test_single_file_deleted(last_check: datetime) -> None:
    state = PathState(CONFIG, existed=True, timestamp=last_check.timestamp())
    CONFIG.unlink()

    result = state.should_nix()

    assert result


def test_single_file_never_present(last_check: datetime) -> None:
    state = PathState(CONFIG, existed=False, timestamp=last_check.timestamp())
    CONFIG.unlink()

    result = state.should_nix()

    assert not result


def test_glob_not_modified(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )

    result = state.should_nix()

    assert not result


def test_glob_file_added(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )
    touch(PACK_DIR / "3.pack", last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert result


def test_glob_file_modified(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )
    touch(PACK2, last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert result


def test_glob_file_deleted(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )
    PACK2.unlink()

    result = state.should_nix()

    assert result


def test_glob_file_different_suffix(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )
    touch(PACK_DIR / "notapack", last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert not result


def test_glob_file_subdir(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )
    touch(PACK_DIR / "subdir" / "3.pack", last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert not result


def test_glob_file_superdir(last_check: datetime) -> None:
    state = GlobState(
        Glob(PACK_DIR, "*.pack", case_sensitive=None),
        seen={PACK1, PACK2},
        timestamp=last_check.timestamp(),
    )
    touch(PACK_DIR.parent / "3.pack", last_check + timedelta(seconds=1))

    result = state.should_nix()

    assert not result
