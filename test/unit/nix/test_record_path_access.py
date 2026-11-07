import sys
import sysconfig
from pathlib import Path

import pytest

from git_graph_branch.nix.cohort import Cohort, live_cohort_context
from git_graph_branch.nix.patching import record_path_access


@pytest.fixture
def package_metadata() -> Path:
    return Path(sysconfig.get_paths()["purelib"]) / "pkg-1.0.dist-info" / "METADATA"


def test_raises_outside_a_nix_context_manager() -> None:
    with pytest.raises(RuntimeError):
        record_path_access(Path("/some/repo/.git/config"))


def test_raises_for_relative_path_outside_a_nix_context_manager() -> None:
    with pytest.raises(RuntimeError):
        record_path_access(Path(".git/config"))


def test_ignores_package_metadata_outside_a_nix_context_manager(
    package_metadata: Path,
) -> None:
    record_path_access(package_metadata)


def test_ignores_sys_path_entry_outside_a_nix_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "path", [*sys.path, "/editable/src"])
    record_path_access(Path("/editable/src/pkg/__init__.py"))


def test_tracks_python_installation_path_in_a_nix_context_manager(
    package_metadata: Path,
) -> None:
    cohort = Cohort()
    with live_cohort_context(cohort):
        record_path_access(package_metadata)
    assert package_metadata in cohort.paths
