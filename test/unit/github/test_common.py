from unittest.mock import Mock

import aiohttp

from git_graph_branch.github.common import error_text


def test_http_error_text_is_the_status_and_reason() -> None:
    error = aiohttp.ClientResponseError(
        Mock(real_url="https://x"), (), status=403, message="rate limited"
    )

    assert error_text(error) == "403 rate limited"


def test_error_without_a_message_is_its_type() -> None:
    assert error_text(TimeoutError()) == "TimeoutError"
