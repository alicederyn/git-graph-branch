import re
from functools import cache
from os import environ
from pathlib import Path
from typing import Iterator

from .path import git_dir

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
    yield git_dir() / "config"


@cache
def config() -> Config:
    config: Config = {}
    for config_file in config_paths():
        if config_file.exists():
            parse_config(config_file, config)

    return config
