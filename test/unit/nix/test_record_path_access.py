import sys
import sysconfig
from collections.abc import Iterator
from pathlib import Path

import pytest

from git_graph_branch.nix.fact import NixError, report_calculation, session
from git_graph_branch.nix.files import file_states
from git_graph_branch.nix.patching import record_path_access


@pytest.fixture
def one_shot() -> Iterator[None]:
    with session(None):
        yield


@pytest.fixture
def package_metadata() -> Path:
    return Path(sysconfig.get_paths()["purelib"]) / "pkg-1.0.dist-info" / "METADATA"


def test_raises_outside_a_report_calculation(one_shot: None) -> None:
    with pytest.raises(NixError):
        record_path_access(Path("/some/repo/.git/config"))


def test_raises_for_relative_path_outside_a_report_calculation(one_shot: None) -> None:
    with pytest.raises(NixError):
        record_path_access(Path(".git/config"))


def test_ignores_package_metadata_outside_a_report_calculation(
    one_shot: None,
    package_metadata: Path,
) -> None:
    record_path_access(package_metadata)


def test_ignores_sys_path_entry_outside_a_report_calculation(
    one_shot: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "path", [*sys.path, "/editable/src"])
    record_path_access(Path("/editable/src/pkg/__init__.py"))


def test_tracks_python_installation_path_in_a_report_calculation(
    one_shot: None, package_metadata: Path
) -> None:
    with report_calculation():
        record_path_access(package_metadata)
    assert package_metadata in file_states
