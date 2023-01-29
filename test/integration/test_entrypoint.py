from datetime import datetime, timedelta
from subprocess import check_call
from textwrap import dedent
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from git_graph_branch import main

from ..unit.git.utils import git_remote_repo, git_test_commit


def repo_setup() -> None:
    start_datetime = datetime(2022, 11, 23, 12, 1, tzinfo=ZoneInfo("Europe/London"))

    old_main = git_test_commit(date=start_datetime)
    main_commit = git_test_commit(date=start_datetime)
    check_call(["git", "checkout", "main", "-b", "feature1"])
    feature1 = git_test_commit(date=start_datetime + timedelta(minutes=2))
    check_call(["git", "checkout", "feature1", "-b", "feature2"])
    old_feature2 = git_test_commit(date=start_datetime + timedelta(minutes=3))
    git_test_commit(date=start_datetime + timedelta(minutes=3))
    check_call(["git", "checkout", "main", "-b", "feature3"])
    git_test_commit(date=start_datetime + timedelta(minutes=4))
    check_call(["git", "checkout", "feature3", "-b", "feature4"])
    git_test_commit(date=start_datetime + timedelta(minutes=1))
    git_remote_repo("upstream", main=main_commit)
    git_remote_repo("origin", main=old_main, feature1=feature1, feature2=old_feature2)
    check_call(["git", "branch", "main", "--set-upstream-to", "upstream/main"])


@pytest.mark.usefixtures("repo")
def test_simple_repository_graph(capsys: pytest.CaptureFixture[str]) -> None:
    repo_setup()
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


@pytest.mark.usefixtures("repo")
@patch("sys.stdout.isatty", new=lambda: True)
def test_simple_repository_graph_tty(capsys: pytest.CaptureFixture[str]) -> None:
    repo_setup()
    expected = """\
        ┬  \x1b[35mfeature4\x1b[0m
        ┼  feature3
        │ ┬  feature2
        ├▶┘  feature1
        ┴  main
    """

    main([])

    out, err = capsys.readouterr()
    assert out == dedent(expected)
    assert err == ""
