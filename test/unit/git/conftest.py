from typing import Iterable

from pytest import fixture

from git_graph_branch import git


@fixture(autouse=True)
def clear_functools_caches() -> Iterable[None]:
    try:
        yield
    finally:
        for f in vars(git).values():
            try:
                f.cache_clear()
            except AttributeError:
                pass
