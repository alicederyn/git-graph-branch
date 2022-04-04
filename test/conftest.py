import os
from pathlib import Path
from subprocess import check_call, check_output
from typing import Iterable

import pytest
from packaging import version


def assert_git_version(minimum_version: str) -> None:
    git_version = version.parse(
        check_output(["git", "--version"], encoding="ascii").removeprefix(
            "git version "
        )
    )
    if git_version < version.parse(minimum_version):
        raise AssertionError(f"Tests require git >= {minimum_version}")


@pytest.fixture
def temp_working_dir(request: pytest.FixtureRequest, tmp_path: Path) -> Iterable[Path]:
    assert_git_version("2.28")  # Needed for `git branch -m` to succeed
    os.chdir(tmp_path)
    try:
        os.mkdir(".git")  # Tests write temp files here
        yield tmp_path
    finally:
        os.chdir(request.config.invocation_params.dir)


@pytest.fixture
def repo(temp_working_dir: Path) -> Iterable[Path]:
    assert_git_version("2.28")  # Needed for `git branch -m` to succeed
    check_call(["git", "init", "--quiet"])
    check_call(["git", "branch", "-m", "main"])
    check_call(["git", "config", "user.email", "unit-test-runner@example.com"])
    check_call(["git", "config", "user.name", "Unit Test Runner"])
    yield temp_working_dir
