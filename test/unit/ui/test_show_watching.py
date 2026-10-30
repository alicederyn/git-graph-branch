import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from git_graph_branch.display import Config
from git_graph_branch.ui import ShowFrame, show_watching


@pytest.fixture(autouse=True)
def app_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("TMUX", raising=False)
    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            yield


def refresh_that_breaks_the_loop(context: dict[str, Any]) -> Any:
    async def refresh(show: ShowFrame) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(loop.call_exception_handler, context)
        await asyncio.Event().wait()

    return refresh


async def test_an_unhandled_loop_exception_exits_with_it() -> None:
    error = ValueError("boom")

    with pytest.raises(ExceptionGroup) as raised:
        await asyncio.wait_for(
            show_watching(
                Config(),
                refresh_that_breaks_the_loop({"message": "", "exception": error}),
            ),
            timeout=5,
        )

    assert raised.value.exceptions == (error,)


async def test_an_unhandled_loop_error_without_an_exception_exits_with_its_message() -> (
    None
):
    with pytest.raises(ExceptionGroup) as raised:
        await asyncio.wait_for(
            show_watching(
                Config(),
                refresh_that_breaks_the_loop({"message": "Task was destroyed"}),
            ),
            timeout=5,
        )

    [exception] = raised.value.exceptions
    assert isinstance(exception, RuntimeError)
    assert str(exception) == "Task was destroyed"
