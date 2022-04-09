import pytest

from git_graph_branch.git import parse_config


def test_empty_config() -> None:
    c = parse_config([])
    assert c == {}


def test_simple_config() -> None:
    lines = [
        "[core]",
        "  ignorecase = true",
        '[remote "origin"]',
        "  url = git@github.com:example/project.git",
        "  fetch = +refs/heads/*:refs/remotes/origin/*",
        '[branch "main"]',
        "  remote = origin",
        "  merge = refs/heads/main",
    ]
    c = parse_config(lines)
    assert c == {
        "core": {"ignorecase": "true"},
        ("remote", "origin"): {
            "url": "git@github.com:example/project.git",
            "fetch": "+refs/heads/*:refs/remotes/origin/*",
        },
        ("branch", "main"): {"remote": "origin", "merge": "refs/heads/main"},
    }


def test_unquoted_escape_handling() -> None:
    lines = [
        '[branch "baz"]',
        r"  merge = refs/heads/a\"b",
    ]
    c = parse_config(lines)
    assert c == {
        ("branch", "baz"): {"merge": 'refs/heads/a"b'},
    }


def test_quote_handling() -> None:
    lines = [
        '[branch "foo#bar"]',
        '  merge = "refs/heads/foo#bar"',
        r'[branch "a\"b"]',
        r'  merge = "refs/heads/a\"b"',
    ]
    c = parse_config(lines)
    assert c == {
        ("branch", "foo#bar"): {"merge": "refs/heads/foo#bar"},
        ("branch", 'a"b'): {"merge": 'refs/heads/a"b'},
    }


def test_comments() -> None:
    lines = ["# Comment 1", "[core]  # Comment 2", "  ignorecase = true  # Comment 3"]
    c = parse_config(lines)
    assert c == {"core": {"ignorecase": "true"}}


def test_missing_section() -> None:
    lines = ["  ignorecase = true"]
    with pytest.raises(Exception, match="Error parsing"):
        parse_config(lines)


def test_missing_bracket() -> None:
    lines = ["[core", "  ignorecase = true"]
    with pytest.raises(Exception, match="Error parsing"):
        parse_config(lines)
