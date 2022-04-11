import re
from functools import cache
from typing import Iterable

from .path import git_dir

Config = dict[str | tuple[str, str], dict[str, str]]


def parse_config(lines: Iterable[str]) -> Config:
    SINGLE_STRING_KEY = re.compile(r"^\[(\S+)\](\s*#.*)?$")
    DOUBLE_STRING_KEY = re.compile(r'^\[(\S+)\s+"([^\\"]*(\\.[^\\"]*)*)"\](\s*#.*)?$')
    KEY_VALUE = re.compile(r"^(\w+)\s*=\s*([^\"#\s]([^#]*[^#\s])?)(\s*#.*)?$")
    KEY_QUOTED_VALUE = re.compile(r'^(\w+)\s*=\s*"([^\\"]*(\\.[^\\"]*)*)"(\s*#.*)?$')
    BLANK = re.compile(r"^(#.*)?$")
    result: Config = {}
    current_dict: dict[str, str] | None = None
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
                raise Exception("Error parsing .git/config\nUnexpected line: " + line)
        else:
            raise Exception("Error parsing .git/config\nUnexpected line: " + line)

    return result


@cache
def config() -> Config:
    config_file = git_dir() / "config"
    return parse_config(config_file.open())
