from types import ModuleType
from typing import Any, Iterable

from pytest import fixture

from git_graph_branch import git


def nested_vars(m: ModuleType, max_depth: int) -> Iterable[Any]:
    for o in vars(m).values():
        if isinstance(o, ModuleType):
            if max_depth > 1:
                yield from nested_vars(o, max_depth - 1)
        else:
            yield o


@fixture(autouse=True)
def clear_functools_caches() -> Iterable[None]:
    try:
        yield
    finally:
        for f in nested_vars(git, max_depth=2):
            try:
                f.cache_clear()
            except AttributeError:
                pass
