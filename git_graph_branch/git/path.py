from functools import cache
from pathlib import Path
from typing import Iterable


def path_and_parents(p: Path) -> Iterable[Path]:
    yield p
    while p.parent != p:
        p = p.parent
        yield p


@cache
def git_working_state() -> Path:
    """Return the git state directory for the current worktree.

    This directory contains the following files and directories:

    ├─ HEAD — the current branch ref or detached commit hash
    ├─ commondir — (linked worktrees only) relative path to the main
    │              git directory
    ├─ gitdir — (linked worktrees only) absolute path back to this
    │           worktree directory
    ├─ index — the staging area
    ├─ logs/HEAD — reflog for HEAD
    ├─┐ refs/
    │ ├─ bisect/ — per-worktree bisect state
    │ ├─ rewritten/ — per-worktree rewritten refs
    │ └─ worktree/ — per-worktree arbitrary refs
    └─ *_HEAD, BISECT_LOG, AUTO_MERGE — transient operation state files

    Note: depending on the git configuration, this may return the same path
    as ``git_common_state``.

    See https://git-scm.com/docs/gitrepository-layout
    """
    for p in path_and_parents(Path.cwd()):
        d = p / ".git"
        if d.is_dir():
            return d
        if d.is_file():
            text = d.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir: "):
                raise Exception(f"Unexpected .git file content: {text}")
            gitdir = Path(text.removeprefix("gitdir: "))
            if not gitdir.is_absolute():
                gitdir = (d.parent / gitdir).resolve()
            return gitdir
    raise Exception("not a git repository (or any of the parent directories): .git")


@cache
def git_common_state() -> Path:
    """Return the common git state directory used by all worktrees.

    This directory contains the following files and directories:

    ├─ branches/ — deprecated shorthand for remote URLs
    ├─ config — repository-level configuration
    ├─ description — repository description (used by gitweb)
    ├─ hooks/ — hook scripts
    ├─ info/ — auxiliary metadata (e.g. ``info/exclude``, ``info/refs``)
    ├─ logs/refs/ — reflogs for branches and remote-tracking refs
    ├─ modules/ — submodule git directories
    ├─ objects/ — loose objects and packfiles
    ├─ packed-refs — file listing refs packed from ``refs/``
    ├─┐ refs/
    │ ├─ heads/ — local branch tips
    │ ├─ remotes/ — remote-tracking branch tips
    │ └─ tags/ — tag references
    ├─ shallow — shallow clone graft points
    └─ worktrees/ — linked worktree state directories

    Note: depending on the git configuration, this may return the same path
    as ``git_working_state``.

    See https://git-scm.com/docs/gitrepository-layout
    """
    worktree = git_working_state()
    commondir_file = worktree / "commondir"
    if commondir_file.is_file():
        commondir = Path(commondir_file.read_text(encoding="utf-8").strip())
        if not commondir.is_absolute():
            commondir = (worktree / commondir).resolve()
        return commondir
    return worktree
