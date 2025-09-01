# coding=utf-8
from datetime import datetime, timedelta
from subprocess import check_call
from textwrap import dedent
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from git_graph_branch.cli import amain

from ..unit.git.utils import git_remote_repo, git_test_commit


def config_setup() -> None:
    check_call(["git", "config", "--global", "remote.pushdefault", "origin"])


def repo_setup() -> None:
    start_datetime = datetime(2022, 11, 23, 12, 1, tzinfo=ZoneInfo("Europe/London"))

    old_main = git_test_commit(date=start_datetime)
    main_commit = git_test_commit(date=start_datetime)
    check_call(["git", "checkout", "main", "-b", "merged.feature"])
    check_call(["git", "checkout", "main", "-b", "feature1"])
    feature1 = git_test_commit(date=start_datetime + timedelta(minutes=2))
    check_call(["git", "checkout", "feature1", "-b", "feature2"])
    old_feature2 = git_test_commit(date=start_datetime + timedelta(minutes=3))
    git_test_commit(date=start_datetime + timedelta(minutes=3))
    check_call(["git", "checkout", "main", "-b", "feature3"])
    git_test_commit(date=start_datetime + timedelta(minutes=4))
    check_call(["git", "checkout", "feature3", "-b", "feature4"])
    check_call(["git", "merge", old_feature2])
    git_test_commit(date=start_datetime + timedelta(minutes=1))
    git_remote_repo("upstream", main=old_main)
    git_remote_repo(
        "origin", main=main_commit, feature1=feature1, feature2=old_feature2
    )
    check_call(["git", "branch", "main", "--set-upstream-to", "upstream/main"])


@pytest.mark.usefixtures("repo")
async def test_simple_repository_graph(capsys: pytest.CaptureFixture[str]) -> None:
    config_setup()
    repo_setup()
    expected = """\
        ┬◀┐  feature4 [1 unmerged]
        ┼ │  feature3
        │ ┼  feature2
        ├▶┘  feature1
        ├▶╴  merged.feature
        ┴  main
    """

    await amain([])

    out, err = capsys.readouterr()
    assert out == dedent(expected)
    assert err == ""


@pytest.mark.usefixtures("repo")
@patch("sys.stdout.isatty", new=lambda: True)
async def test_simple_repository_graph_tty(capsys: pytest.CaptureFixture[str]) -> None:
    config_setup()
    repo_setup()
    expected = """\
        ┬◀┐  \x1b[1;35mfeature4\x1b[0m\x1b[1;31m [1 unmerged]\x1b[0m
        ┼ │  feature3
        │ ┼  feature2 🔶
        ├▶┘  feature1 🔷
        ├▶╴  \x1b[37mmerged.feature\x1b[0m
        ┴  main 🔷
    """

    await amain([])

    out, err = capsys.readouterr()
    assert out == dedent(expected)
    assert err == ""
