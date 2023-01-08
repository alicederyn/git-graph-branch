from __future__ import annotations

import functools
import os
from pathlib import Path
from subprocess import check_call, check_output
from typing import Callable, Iterable, TypeVar

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
