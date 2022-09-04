from subprocess import check_output


def touch(filename: str) -> None:
    with open(filename, "w"):
        pass


def head_hash() -> str:
    return check_output(["git", "rev-parse", "HEAD"], encoding="ascii").strip()
