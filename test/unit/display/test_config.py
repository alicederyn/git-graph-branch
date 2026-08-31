from git_graph_branch.display import Config


def test_explicit_values_override_tty_defaults() -> None:
    config = Config(is_tty=True, color=False, remote_icons=False)

    assert config.color is False
    assert config.remote_icons is False
