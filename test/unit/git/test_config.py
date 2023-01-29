from pathlib import Path
from textwrap import dedent

from git_graph_branch.git.config import config


def test_combine_config_files(home_dir: Path, temp_working_dir: Path) -> None:
    global_config = """\
        [user]
          name = Joe Bloggs
          email = joeb12@example.com

        [remote]
          pushdefault = origin
    """
    repo_config = """\
        [user]
          email = joe.bloggs@example.org

        [remote "origin"]
          url = https://example.org/joebloggs/some-repo.git
    """
    (home_dir / ".gitconfig").write_text(dedent(global_config))
    (temp_working_dir / ".git" / "config").write_text(dedent(repo_config))

    all_config = config()

    assert all_config == {
        "user": {
            "name": "Joe Bloggs",
            "email": "joe.bloggs@example.org",
        },
        "remote": {
            "pushdefault": "origin",
        },
        ("remote", "origin"): {
            "url": "https://example.org/joebloggs/some-repo.git",
        },
    }
