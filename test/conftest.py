from __future__ import annotations

import functools
import os
from pathlib import Path
from subprocess import check_call, check_output
from textwrap import dedent
from typing import Callable, Iterable, TypeVar
from unittest.mock import patch

import hypothesis
import pytest
from packaging import version

T = TypeVar("T")
cache_clear_fns: list[Callable[[], None]] = []

hypothesis.settings.register_profile("thorough", max_examples=1_000)


def monkeypatch_functools() -> None:
    original_cache = functools.cache

    def tracking_cache(
        user_function: Callable[..., T], /
    ) -> functools._lru_cache_wrapper[T]:
        cached_fn = original_cache(user_function)
        cache_clear_fns.append(cached_fn.cache_clear)
        return cached_fn

    functools.cache = tracking_cache


@pytest.hookimpl(hookwrapper=True)  # type: ignore
def pytest_collection() -> Iterable[None]:
    monkeypatch_functools()
    yield


@pytest.fixture(autouse=True)
def clear_functools_caches() -> Iterable[None]:
    try:
        yield
    finally:
        for cache_clear in cache_clear_fns:
            cache_clear()


def assert_git_version(minimum_version: str) -> None:
    git_version = version.parse(
        check_output(["git", "--version"], encoding="ascii").removeprefix(
            "git version "
        )
    )
    if git_version < version.parse(minimum_version):
        raise AssertionError(f"Tests require git >= {minimum_version}")


@pytest.fixture
def temp_working_dir(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterable[Path]:
    assert_git_version("2.28")  # Needed for `git branch -m` to succeed
    tmp_path = tmp_path_factory.mktemp("repo")
    os.chdir(tmp_path)
    try:
        os.mkdir(".git")  # Tests write temp files here
        yield tmp_path
    finally:
        os.chdir(request.config.invocation_params.dir)


@pytest.fixture
def home_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterable[Path]:
    home_dir = Path(tmp_path_factory.mktemp("home"))
    monkeypatch.setenv("HOME", str(home_dir.absolute()))
    with patch.object(Path, "home", new=lambda: home_dir):
        yield home_dir


@pytest.fixture
def repo(home_dir: Path, temp_working_dir: Path) -> Iterable[Path]:
    global_config = """\
        [branch]
          autosetupmerge = always
        [init]
          defaultBranch = main
    """
    (home_dir / ".gitconfig").write_text(dedent(global_config))
    assert_git_version("2.28")  # Needed for `git branch -m` to succeed
    check_call(["git", "config", "--global", "init.defaultBranch", "main"])
    check_call(["git", "init", "--quiet"])
    check_call(["git", "branch", "-m", "main"])
    check_call(["git", "config", "user.email", "unit-test-runner@example.com"])
    check_call(["git", "config", "user.name", "Unit Test Runner"])
    yield temp_working_dir
