import re
from functools import cache
from os import environ
from pathlib import Path
from typing import Iterator
from urllib.parse import SplitResult, urlsplit

from .path import git_common_state

Config = dict[str | tuple[str, str], dict[str, str]]


def parse_config(path: Path, result: Config) -> None:
    SINGLE_STRING_KEY = re.compile(r"^\[(\S+)\](\s*#.*)?$")
    DOUBLE_STRING_KEY = re.compile(r'^\[(\S+)\s+"([^\\"]*(\\.[^\\"]*)*)"\](\s*#.*)?$')
    KEY_VALUE = re.compile(r"^([-\w]+)\s*=\s*([^\"#\s]([^#]*[^#\s])?)(\s*#.*)?$")
    KEY_QUOTED_VALUE = re.compile(r'^(\w+)\s*=\s*"([^\\"]*(\\.[^\\"]*)*)"(\s*#.*)?$')
    BLANK = re.compile(r"^(#.*)?$")
    current_dict: dict[str, str] | None = None
    with path.open() as lines:
        for line in lines:
            line = line.strip()
            if m := SINGLE_STRING_KEY.match(line):
                key = m.group(1)
                current_dict = result.setdefault(key, {})
            elif m := DOUBLE_STRING_KEY.match(line):
                key = (m.group(1), m.group(2).encode("utf-8").decode("unicode_escape"))
                current_dict = result.setdefault(key, {})
            elif BLANK.match(line):
                pass
            elif current_dict is not None:
                if m := (KEY_VALUE.match(line) or KEY_QUOTED_VALUE.match(line)):
                    current_dict[m.group(1)] = (
                        m.group(2).encode("utf-8").decode("unicode_escape")
                    )
                else:
                    raise Exception(f"Error parsing {path}\nUnexpected line: {line}")
            else:
                raise Exception(f"Error parsing {path}\nUnexpected line: {line}")


def str_to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() in {"yes", "on", "true", "1"}:
        return True
    if value.lower() in {"no", "off", "false", "0"}:
        return False
    return None


def environ_bool(name: str, default: bool) -> bool:
    value = environ.get(name)
    if value is None:
        return default
    value_bool = str_to_bool(value)
    if value_bool is None:
        raise Exception(f'Unexpected value for ${{{name}}}: "{value}"')
    return value_bool


def environ_optional_path(name: str) -> Path | None:
    value = environ.get(name)
    if value is None:
        return None
    value_path = Path(value)
    if not value_path.exists():
        raise Exception(f'No file found at ${{{name}}}: "{value}"')
    return value_path


def config_paths() -> Iterator[Path]:
    if not environ_bool("GIT_CONFIG_NOSYSTEM", False):
        yield environ_optional_path("GIT_CONFIG_GLOBAL") or Path("/etc/gitconfig")
    if git_config_system := environ_optional_path("GIT_CONFIG_SYSTEM"):
        yield git_config_system
    else:
        xdg_config_home = Path(environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        yield xdg_config_home / "git" / "config"
        yield Path.home() / ".gitconfig"
    yield git_common_state() / "config"


@cache
def config() -> Config:
    config: Config = {}
    for config_file in config_paths():
        if config_file.exists():
            parse_config(config_file, config)

    return config


def remote_push_default() -> str | None:
    return config().get("remote", {}).get("pushdefault")


def remote_url(remote: str) -> str | None:
    return config().get(("remote", remote), {}).get("url")


DEFAULT_PORTS = {"http": 80, "https": 443}


def url_matches(pattern: SplitResult, url: SplitResult) -> bool:
    """Whether a `[http "<url>"]` section applies to url.

    Follows git-config's rules: the scheme, host, port and user must match, a `*`
    matches one host label, and the path must match a whole number of segments.
    """
    if pattern.scheme != url.scheme:
        return False
    if pattern.username and pattern.username != url.username:
        return False
    pattern_labels = (pattern.hostname or "").split(".")
    labels = (url.hostname or "").split(".")
    if len(pattern_labels) != len(labels) or any(
        p not in ("*", label) for p, label in zip(pattern_labels, labels)
    ):
        return False
    default_port = DEFAULT_PORTS.get(url.scheme)
    if (pattern.port or default_port) != (url.port or default_port):
        return False
    path = pattern.path.rstrip("/")
    return not path or url.path == path or url.path.startswith(path + "/")


def http_config(url: str) -> dict[str, str]:
    """The http.* settings that git uses for url, without the `http.` prefix.

    Keys are lowercase. A more specific `[http "<url>"]` section wins.
    """
    target = urlsplit(url)
    sections: list[tuple[int, dict[str, str]]] = [(-1, config().get("http", {}))]
    for key, values in config().items():
        if isinstance(key, tuple) and key[0] == "http":
            pattern = urlsplit(key[1])
            if url_matches(pattern, target):
                sections.append((len(pattern.path.rstrip("/")), values))
    result: dict[str, str] = {}
    for _, values in sorted(sections, key=lambda section: section[0]):
        result.update((name.lower(), value) for name, value in values.items())
    return result
