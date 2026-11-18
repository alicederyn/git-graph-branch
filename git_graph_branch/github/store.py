"""Which remote-tracking branches probably came from a push from this machine
(ADR 8).

No query can tell that a branch on GitHub was created by a push from this
machine, so the GitHub layer records it from what git showed in earlier
calculations.
"""

from collections.abc import Hashable
from dataclasses import dataclass, field

from ..nix.fact import Fact

type RemoteBranchName = tuple[str, str]
"""The remote, and the name of the branch on the remote."""


@dataclass(eq=False)
class Store:
    fact: Fact
    remote_branches: frozenset[RemoteBranchName]
    local_branches: frozenset[str]
    just_pushed: dict[RemoteBranchName, set[Hashable]] = field(default_factory=dict)
    """Each just-pushed branch, with the loads of it that gave a result."""


store: Store | None = None


def read_branches(
    remote_branches: frozenset[RemoteBranchName], local_branches: frozenset[str]
) -> None:
    """Change the store from the branches that exist now.

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
        for branch in remote_branches - store.remote_branches:
            # A push usually gives the remote branch the name of a local branch
            # that existed before the push
            if branch[1] in store.local_branches:
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
