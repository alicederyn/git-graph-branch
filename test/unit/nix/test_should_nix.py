import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from git_graph_branch.nix.cohort import Cohort, Glob
from git_graph_branch.nix.polling import should_nix

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
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.paths.add(CONFIG)
    last_seen = {CONFIG}

    result = should_nix(cohort, last_seen, last_check)

    assert not result


def test_single_file_created(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.paths.add(CONFIG)
    touch(CONFIG, last_check + timedelta(seconds=1))

    result = should_nix(cohort, set(), last_check)

    assert result


def test_single_file_modified(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.paths.add(CONFIG)
    touch(CONFIG, last_check + timedelta(seconds=1))
    last_seen = {CONFIG}

    result = should_nix(cohort, last_seen, last_check)

    assert result


def test_single_file_deleted(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.paths.add(CONFIG)
    CONFIG.unlink()
    last_seen = {CONFIG}

    result = should_nix(cohort, last_seen, last_check)

    assert result


def test_single_file_never_present(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.paths.add(CONFIG)
    CONFIG.unlink()

    result = should_nix(cohort, set(), last_check)

    assert not result


def test_glob_not_modified(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert not result


def test_glob_file_added(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    touch(PACK_DIR / "3.pack", last_check + timedelta(seconds=1))
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert result


def test_glob_file_modified(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    touch(PACK2, last_check + timedelta(seconds=1))
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert result


def test_glob_file_deleted(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    PACK2.unlink()
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert result


def test_glob_file_different_suffix(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    touch(PACK_DIR / "notapack", last_check + timedelta(seconds=1))
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert not result


def test_glob_file_subdir(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    touch(PACK_DIR / "subdir" / "3.pack", last_check + timedelta(seconds=1))
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert not result


def test_glob_file_superdir(last_check: datetime) -> None:
    nixer = Mock()
    cohort = Cohort(nix=nixer)
    cohort.globs.add(Glob(PACK_DIR, "*.pack", case_sensitive=None))
    touch(PACK_DIR.parent / "3.pack", last_check + timedelta(seconds=1))
    last_seen = {PACK1, PACK2}

    result = should_nix(cohort, last_seen, last_check)

    assert not result
