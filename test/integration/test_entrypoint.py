from datetime import datetime, timedelta
from subprocess import check_call
from textwrap import dedent
from zoneinfo import ZoneInfo

import pytest

from git_graph_branch import main

from ..unit.git.utils import git_test_commit


@pytest.mark.usefixtures("repo")
def test_simple_repository_graph(capsys: pytest.CaptureFixture[str]) -> None:
    start_datetime = datetime(2022, 11, 23, 12, 1, tzinfo=ZoneInfo("Europe/London"))

    git_test_commit(date=start_datetime)
    check_call(["git", "checkout", "main", "-b", "feature1"])
    git_test_commit(date=start_datetime + timedelta(minutes=2))
    check_call(["git", "checkout", "feature1", "-b", "feature2"])
    git_test_commit(date=start_datetime + timedelta(minutes=3))
    check_call(["git", "checkout", "main", "-b", "feature3"])
    git_test_commit(date=start_datetime + timedelta(minutes=4))
    check_call(["git", "checkout", "feature3", "-b", "feature4"])
    git_test_commit(date=start_datetime + timedelta(minutes=1))
    expected = """\
        ┬  feature4
        ┼  feature3
        │ ┬  feature2
        ├▶┘  feature1
        ┴  main
    """

    main([])

    out, err = capsys.readouterr()
    assert out == dedent(expected)
    assert err == ""
