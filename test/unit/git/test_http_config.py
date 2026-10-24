from pathlib import Path
from textwrap import dedent

from git_graph_branch.git.config import http_config, remote_url


def test_remote_url(repo: Path) -> None:
    (repo / ".git" / "config").write_text(
        dedent("""\
            [remote "origin"]
              url = git@github.com:alicederyn/example.git
        """)
    )

    assert remote_url("origin") == "git@github.com:alicederyn/example.git"
    assert remote_url("upstream") is None


def test_http_config_uses_matching_url_sections(home_dir: Path, repo: Path) -> None:
    (home_dir / ".gitconfig").write_text(
        dedent("""\
            [http]
              sslVerify = true
              proxy = http://default-proxy:80
            [http "https://github.com"]
              proxy = http://github-proxy:81
              sslCAInfo = /etc/ca.crt
            [http "https://github.com/alicederyn"]
              proxy = http://alice-proxy:82
            [http "https://example.com"]
              proxy = http://example-proxy:83
        """)
    )

    assert http_config("https://github.com") == {
        "sslverify": "true",
        "proxy": "http://github-proxy:81",
        "sslcainfo": "/etc/ca.crt",
    }
    assert http_config("https://github.com/alicederyn/repo")["proxy"] == (
        "http://alice-proxy:82"
    )
    assert http_config("https://github.com/alicederyny")["proxy"] == (
        "http://github-proxy:81"
    )
    assert http_config("https://api.github.com/graphql")["proxy"] == (
        "http://default-proxy:80"
    )


def test_http_config_host_wildcard_matches_one_label(
    home_dir: Path, repo: Path
) -> None:
    (home_dir / ".gitconfig").write_text(
        dedent("""\
            [http "https://*.example.com"]
              proxy = http://proxy:80
        """)
    )

    assert http_config("https://api.example.com")["proxy"] == "http://proxy:80"
    assert http_config("https://example.com") == {}
    assert http_config("https://a.b.example.com") == {}


def test_http_config_matches_scheme_port_and_user(home_dir: Path, repo: Path) -> None:
    (home_dir / ".gitconfig").write_text(
        dedent("""\
            [http "https://alice@example.com:443"]
              proxy = http://proxy:80
        """)
    )

    assert http_config("https://alice@example.com")["proxy"] == "http://proxy:80"
    assert http_config("https://bob@example.com") == {}
    assert http_config("http://alice@example.com") == {}
    assert http_config("https://alice@example.com:8443") == {}
