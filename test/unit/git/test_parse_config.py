from pathlib import Path
from textwrap import dedent

import pytest

from git_graph_branch.git.config import Config, parse_config


def test_empty_config(tmp_path: Path) -> None:
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("")
    c: Config = {}
    parse_config(gitconfig, c)
    assert c == {}


def test_simple_config(tmp_path: Path) -> None:
    config_text = """\
        [core]
        ignorecase = true
        [remote "origin"]
        url = git@github.com:example/project.git
        fetch = +refs/heads/*:refs/remotes/origin/*
        [branch "main"]
        remote = origin
        merge = refs/heads/main
    """
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(dedent(config_text))
    c: Config = {}
    parse_config(gitconfig, c)
    assert c == {
        "core": {"ignorecase": "true"},
        ("remote", "origin"): {
            "url": "git@github.com:example/project.git",
            "fetch": "+refs/heads/*:refs/remotes/origin/*",
        },
        ("branch", "main"): {"remote": "origin", "merge": "refs/heads/main"},
    }


def test_unquoted_escape_handling(tmp_path: Path) -> None:
    config_text = r"""
        [branch "baz"]
          merge = refs/heads/a\"b
    """
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(dedent(config_text[1:]))
    c: Config = {}
    parse_config(gitconfig, c)
    assert c == {
        ("branch", "baz"): {"merge": 'refs/heads/a"b'},
    }


def test_quote_handling(tmp_path: Path) -> None:
    config_text = r"""
        [branch "foo#bar"]
          merge = "refs/heads/foo#bar"
        [branch "a\"b"]
          merge = "refs/heads/a\"b"
    """
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(dedent(config_text[1:]))
    c: Config = {}
    parse_config(gitconfig, c)
    assert c == {
        ("branch", "foo#bar"): {"merge": "refs/heads/foo#bar"},
        ("branch", 'a"b'): {"merge": 'refs/heads/a"b'},
    }


def test_comments(tmp_path: Path) -> None:
    config_text = """\
        # Comment 1
        [core]  # Comment 2
          ignorecase = true  # Comment 3
    """
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(dedent(config_text))
    c: Config = {}
    parse_config(gitconfig, c)
    assert c == {"core": {"ignorecase": "true"}}


def test_missing_section(tmp_path: Path) -> None:
    config_text = "  ignorecase = true"
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(config_text)
    c: Config = {}
    with pytest.raises(Exception, match="Error parsing"):
        parse_config(gitconfig, c)


def test_missing_bracket(tmp_path: Path) -> None:
    config_text = """\
        [core
          ignorecase = true
    """
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(config_text)
    c: Config = {}
    with pytest.raises(Exception, match="Error parsing"):
        parse_config(gitconfig, c)
