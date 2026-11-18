"""Which remote-tracking branches probably came from a push from this machine
(ADR 8).

No query can tell that a branch on GitHub was created by a push from this
machine, so the GitHub layer records it from what git showed in earlier
calculations.
"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field

from ..nix.fact import Fact

type RemoteBranchName = tuple[str, str]
"""The remote, and the name of the branch on the remote."""


@dataclass(eq=False)
class Store:
    fact: Fact
    remote_branches: Mapping[RemoteBranchName, str]
    """The commit of each remote-tracking branch at the last read."""
    local_branches: Mapping[str, str]
    """The commit of each local branch at the last read."""
    just_pushed: dict[RemoteBranchName, set[Hashable]] = field(default_factory=dict)
    """Each just-pushed branch, with the loads of it that gave a result."""


store: Store | None = None


def read_branches(
    remote_branches: Mapping[RemoteBranchName, str], local_branches: Mapping[str, str]
) -> None:
    """Change the store from the branches that exist now, with their commits.

    Must be called in a nix report calculation. A second read of the same
    branches changes nothing. Nothing nixes the store, as the caller also reads
    the branches, and a change to them nixes the calculation.
    """
    global store
    if (
        store is not None
        and remote_branches is store.remote_branches
        and local_branches is store.local_branches
    ):
        store.fact.record_use()
        return
    if store is None:
        store = Store(Fact(), remote_branches, local_branches)
        store.fact.on_moot(drop, store)
    else:
        for branch, commit in remote_branches.items():
            # A push usually gives the remote branch the name of a local branch
            # that existed before the push, and the commit that the local branch
            # points to after it
            if (
                branch not in store.remote_branches
                and branch[1] in store.local_branches
                and local_branches.get(branch[1]) == commit
            ):
                store.just_pushed.setdefault(branch, set())
        for branch in list(store.just_pushed):
            if branch not in remote_branches or branch[1] not in local_branches:
                del store.just_pushed[branch]
        store.remote_branches = remote_branches
        store.local_branches = local_branches
    store.fact.record_use()


def assumes_no_pr(branch: RemoteBranchName, load: Hashable, pending: bool) -> bool:
    """Whether a load of branch must show no PR, as this machine probably pushed
    the branch for the first time, and the load has given no result since then.

    Call it with pending false when the load has a result, so that later results
    of the same load are used, also if its entry is made again.
    """
    loaded = store.just_pushed.get(branch) if store else None
    if loaded is None:
        return False
    if not pending:
        loaded.add(load)
        return False
    return load not in loaded


def forget_push(branch: RemoteBranchName) -> None:
    """Take branch out of the just-pushed set, as a load found a PR for it."""
    if store is not None:
        store.just_pushed.pop(branch, None)


def drop(dropped: Store) -> None:
    global store
    if store is dropped:
        store = None
