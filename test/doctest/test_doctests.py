import doctest
from types import ModuleType

import pytest

import git_graph_branch.dag as dag


def collect_doctests(*modules: ModuleType) -> list[object]:
    finder = doctest.DocTestFinder(exclude_empty=False)
    return [
        pytest.param(t, id=t.name)
        for module in modules
        for t in finder.find(module)
        if t.examples
    ]


def run_doctest(test: doctest.DocTest) -> doctest.TestResults:
    runner = doctest.DocTestRunner(
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE
    )
    runner.run(test)
    return runner.summarize(verbose=False)


@pytest.mark.parametrize("test", collect_doctests(dag))
def test_docstrings(test: doctest.DocTest) -> None:
    result = run_doctest(test)
    if result.failed:
        pytest.fail("Doctest failed")
