from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from git_graph_branch import display
from git_graph_branch.display import Config, PrStatus, pr_statuses
from git_graph_branch.git import Branch


@pytest.fixture(autouse=True)
def pr_check_status() -> Iterator[AsyncMock]:
    with patch.object(display, "pr_check_status", new=AsyncMock()) as mock:
        yield mock


@pytest.fixture(autouse=True)
def pr_review_status() -> Iterator[AsyncMock]:
    with patch.object(display, "pr_review_status", new=AsyncMock()) as mock:
        yield mock


def test_explicit_values_override_tty_defaults() -> None:
    config = Config(is_tty=True, color=False, remote_icons=False)

    assert config.color is False
    assert config.remote_icons is False


@pytest.mark.parametrize("is_tty", [True, False])
def test_pr_icons_default_to_tty(is_tty: bool) -> None:
    assert Config(is_tty=is_tty).pr_icons is is_tty


async def test_no_pr_icons_loads_no_pr_statuses(
    pr_check_status: AsyncMock, pr_review_status: AsyncMock
) -> None:
    config = Config(is_tty=True, pr_icons=False)

    statuses = await pr_statuses(config, [Mock(spec=Branch)])

    assert statuses == [PrStatus()]
    pr_check_status.assert_not_called()
    pr_review_status.assert_not_called()
