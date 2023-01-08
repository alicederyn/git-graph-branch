from datetime import datetime
from subprocess import check_call, check_output
from typing import Optional


def head_hash() -> str:
    return check_output(["git", "rev-parse", "HEAD"], encoding="ascii").strip()


def git_test_commit(
    *filenames: str,
    amend: bool = False,
    date: Optional[datetime] = None,
    message: Optional[str] = None,
) -> str:
    """Creates a test commit, appending to given files.

    Parameters
    ----------
    amend
        Amend the previous commit instead of creating a new one.
    date
        Author date.
    message
        The commit message. Default varies based on the action performed.
    """
    for filename in filenames:
        with open(filename, "a") as f:
            f.write("Append a line")
        check_call(["git", "add", filename])
    if amend and message:
        args = ["--amend", "-m", message]
    elif amend:
        args = ["--amend", "--no-edit"]
    elif filenames:
        args = ["-m", message or f"Modified {', '.join(filenames)}"]
    else:
        args = ["--allow-empty", "-m", message or "Blank commit"]
    if date:
        args.extend(["--date", date.isoformat()])
    check_call(["git", "commit", "-q", *args])
    return head_hash()


def git_test_merge(*refs: str) -> str:
    """Create a test merge commit."""
    check_call(["git", "merge", *refs, "-qm", f"Merge {', '.join(refs)}"])
    return head_hash()
