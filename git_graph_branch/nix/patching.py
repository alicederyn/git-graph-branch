from __future__ import annotations

import functools
from collections import OrderedDict
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Hashable, Iterator

from .fact import Fact
from .files import Glob, record_glob, record_path


def wrap_simple_path_method[**P, T](orig_method: Callable[P, T]) -> Callable[P, T]:
    @wraps(orig_method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        path = args[0]
        assert isinstance(path, Path)
        record_path(path)
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
        results = list(original_glob(self, pattern, case_sensitive=case_sensitive))
        record_glob(Glob(self, str(pattern), case_sensitive), results)
        yield from results

    setattr(Path, "glob", glob)


def nix_cache(
    user_function: Callable[..., Any], maxsize: int | None, typed: bool
) -> Any:
    """Cache each result as a fact, so that nix drops only the entries that change."""
    entries: OrderedDict[Hashable, tuple[Fact, Any]] = OrderedDict()
    hits = misses = 0

    def drop(key: Hashable, fact: Fact) -> None:
        entry = entries.get(key)
        if entry is not None and entry[0] is fact:
            del entries[key]

    @wraps(user_function)
    def cache_wrapper(*args: Any, **kwargs: Any) -> Any:
        nonlocal hits, misses
        key = functools._make_key(args, kwargs, typed)
        entry = entries.get(key)
        if entry is not None:
            hits += 1
            entries.move_to_end(key)
            fact, value = entry
            fact.record_use()
            return value
        misses += 1
        fact = Fact()
        fact.on_nix(fact.on_moot(drop, key, fact))
        with fact.calculation():
            value = user_function(*args, **kwargs)
        entries[key] = (fact, value)
        if maxsize is not None and len(entries) > maxsize:
            entries.popitem(last=False)
        return value

    def cache_info() -> functools._CacheInfo:
        return functools._CacheInfo(hits, misses, maxsize, len(entries))

    def cache_clear() -> None:
        nonlocal hits, misses
        entries.clear()
        hits = misses = 0

    def cache_parameters() -> dict[str, Any]:
        return {"maxsize": maxsize, "typed": typed}

    result: Any = cache_wrapper  # Disable type validation
    result.cache_info = cache_info
    result.cache_clear = cache_clear
    result.cache_parameters = cache_parameters
    return result


def install_lru_cache_hook() -> None:
    @wraps(functools.lru_cache)
    def lru_cache(maxsize: Any = 128, typed: bool = False) -> Any:
        if callable(maxsize):
            return nix_cache(maxsize, 128, typed)
        if maxsize is not None:
            maxsize = max(maxsize, 0)
        return lambda user_function: nix_cache(user_function, maxsize, typed)

    setattr(functools, "lru_cache", lru_cache)


def install() -> None:
    """Monkeypatch common libraries to track filesystem access and data caching.

    This must be called before loading any modules that access the filesystem or use data caching,
    otherwise the patching will not work.
    """
    install_path_hooks()
    install_glob_hook()
    install_lru_cache_hook()
