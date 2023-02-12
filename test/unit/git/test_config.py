from pathlib import Path
from textwrap import dedent

from git_graph_branch.git.config import config
from git_graph_branch.ixnay import SingleUseNixer
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver


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

    all_config = config(SingleUseNixer())

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


def test_modify_repo_config_invalidates(
    home_dir: Path, temp_working_dir: Path, manual_observer: ManualObserver
) -> None:
    global_config = """\
        [remote]
          pushdefault = origin
    """
    repo_config = """\
        [remote "origin"]
          url = https://example.org/joebloggs/some-repo.git
    """
    (home_dir / ".gitconfig").write_text(dedent(global_config))
    (temp_working_dir / ".git" / "config").write_text(dedent(repo_config))

    nixer = FakeNixer()
    result = config(nixer)
    assert result.keys() == {"remote", ("remote", "origin")}
    (temp_working_dir / ".git" / "config").write_text(
        dedent(repo_config.replace("origin", "upstream"))
    )
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    result = config(FakeNixer())
    assert result.keys() == {"remote", ("remote", "upstream")}


def test_modify_global_config_invalidates(
    home_dir: Path, temp_working_dir: Path, manual_observer: ManualObserver
) -> None:
    global_config = """\
        [remote]
          pushdefault = origin
    """
    repo_config = """\
        [remote "origin"]
          url = https://example.org/joebloggs/some-repo.git
    """
    (home_dir / ".gitconfig").write_text(dedent(global_config))
    (temp_working_dir / ".git" / "config").write_text(dedent(repo_config))

    nixer = FakeNixer()
    result = config(nixer)
    assert result["remote"]["pushdefault"] == "origin"
    (home_dir / ".gitconfig").write_text(
        dedent(global_config.replace("origin", "upstream"))
    )
    manual_observer.check_for_changes()
    assert nixer.is_nixed
    result = config(FakeNixer())
    assert result["remote"]["pushdefault"] == "upstream"
