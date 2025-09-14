from __future__ import annotations

import functools
import sys
from functools import wraps
from pathlib import Path
from stat import S_ISDIR
from typing import Any, Callable, Iterator

from . import console
from .cohort import Glob, active_cohort

# Capture Path methods before we patch them
# Be careful not to capture methods that call other methods
PATH_GLOB = Path.glob
PATH_STAT = Path.stat


def is_dir(path: Path) -> bool:
    """Determine if path is a directory.

    Reimplemented as Path.is_dir calls Path.stat
    """
    try:
        return S_ISDIR(PATH_STAT(path, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return False


def record_path_access(path: Path) -> None:
    cohort = active_cohort.get()
    if cohort is not None:
        cohort.paths.add(path)
        try:
            PATH_STAT(path)
            cohort.seen.add(path)
        except FileNotFoundError:
            pass


def wrap_simple_path_method[**P, T](orig_method: Callable[P, T]) -> Callable[P, T]:
    @wraps(orig_method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        path = args[0]
        assert isinstance(path, Path)
        record_path_access(path)
        return orig_method(*args, **kwargs)

    return wrapper


def install_path_hooks() -> None:
    setattr(Path, "exists", wrap_simple_path_method(Path.exists))
    setattr(Path, "is_dir", wrap_simple_path_method(Path.is_dir))
    setattr(Path, "is_file", wrap_simple_path_method(Path.is_file))
    setattr(Path, "open", wrap_simple_path_method(Path.open))
    setattr(Path, "read_bytes", wrap_simple_path_method(Path.read_bytes))
    setattr(Path, "read_text", wrap_simple_path_method(Path.read_text))
    setattr(Path, "stat", wrap_simple_path_method(Path.stat))
    setattr(Path, "write_bytes", wrap_simple_path_method(Path.write_bytes))
    setattr(Path, "write_text", wrap_simple_path_method(Path.write_text))


def install_glob_hook() -> None:
    original_glob = Path.glob

    @wraps(Path.glob)
    def glob(
        self: Path,
        pattern: str,
        *,
        case_sensitive: bool | None = None,
        recurse_symlinks: bool = False,
    ) -> Iterator[Path]:
        if recurse_symlinks:
            raise RuntimeError("nix does not support recurse_symlinks")
        cohort = active_cohort.get()
        results = original_glob(self, pattern, case_sensitive=case_sensitive)
        if cohort is None:
            yield from results
        else:
            cohort.globs.add(Glob(self, str(pattern), case_sensitive=case_sensitive))
            for path in results:
                cohort.seen.add(path)
                yield path

    setattr(Path, "glob", glob)


def install_lru_cache_hook() -> None:
    original_lru_cache = functools.lru_cache

    @wraps(original_lru_cache)
    def lru_cache(
        *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        create_cache_wrapper = original_lru_cache(*args, **kwargs)

        @wraps(create_cache_wrapper)
        def create_cache(user_function: Callable[..., Any]) -> Any:
            original_cache_wrapper = create_cache_wrapper(user_function)

            @wraps(user_function)
            def cache_wrapper(*args: Any, **kwargs: Any) -> Any:
                cohort = active_cohort.get()
                if cohort is not None:
                    cohort.on_nix.append(original_cache_wrapper.cache_clear)
                return original_cache_wrapper(*args, **kwargs)

            result: Any = cache_wrapper  # Disable type validation
            result.cache_clear = original_cache_wrapper.cache_clear
            result.cache_info = original_cache_wrapper.cache_info
            result.cache_parameters = original_cache_wrapper.cache_parameters
            return result

        return create_cache

    setattr(functools, "lru_cache", lru_cache)


def install_console_hooks() -> None:
    out = console.NixableIO(sys.stdout)
    err = console.NixableIO(sys.stderr, hold_io=True)
    sys.stdout = console._nixable_stdout = out
    sys.stderr = console._nixable_stderr = err


def install() -> None:
    """Monkeypatch common libraries to track filesystem access and data caching.

    This must be called before loading any modules that access the filesystem or use data caching,
    otherwise the patching will not work.
    """
    install_path_hooks()
    install_glob_hook()
    install_lru_cache_hook()
    install_console_hooks()
