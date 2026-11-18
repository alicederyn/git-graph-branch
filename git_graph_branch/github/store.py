"""Whether each push target had a remote-tracking branch (ADR 8).

No query can tell that a branch on GitHub was created by a push from this
machine, so the GitHub layer records it from what git showed in earlier
calculations.
"""

from collections.abc import Hashable
from dataclasses import dataclass, field
from enum import Enum, auto

from ..nix.fact import Fact


class PushState(Enum):
    ABSENT = auto()
    """The last read found no remote-tracking branch."""
    PUSHED = auto()
    """The remote-tracking branch appeared after a read found none, so this
    machine probably pushed the branch for the first time, and it has no PR."""
    PRESENT = auto()
    """The read found a remote-tracking branch, and the record was missing or
    present."""


@dataclass(eq=False)
class Record:
    key: Hashable
    fact: Fact
    state: PushState
    loaded: set[Hashable] = field(default_factory=set)
    """The loads that gave a result since the state became pushed."""


records: dict[Hashable, Record] = {}


def next_state(state: PushState | None, tracking_exists: bool) -> PushState:
    if not tracking_exists:
        return PushState.ABSENT
    if state in (PushState.ABSENT, PushState.PUSHED):
        return PushState.PUSHED
    return PushState.PRESENT


def read_push_state(key: Hashable, tracking_exists: bool) -> PushState:
    """Change the record of a push target from what git shows now, and return it.

    Must be called in a nix report calculation. A second read that finds the same
    gives the same state. Nothing nixes a record, as the caller also reads the
    remote-tracking branch, and a change to it nixes the calculation.
    """
    record = records.get(key)
    if record is None:
        record = records[key] = Record(key, Fact(), next_state(None, tracking_exists))
        record.fact.on_moot(drop, record)
    else:
        state = next_state(record.state, tracking_exists)
        if state is PushState.PUSHED and record.state is not PushState.PUSHED:
            record.loaded = set()
        record.state = state
    record.fact.record_use()
    return record.state


def assumes_no_pr(key: Hashable, load: Hashable, pending: bool) -> bool:
    """Whether a load must show no PR, as this machine probably pushed the branch
    for the first time, and the load has given no result since the push.

    Call it with pending false when the load has a result, so that later results
    of the same load are used, also if its entry is made again.
    """
    record = records.get(key)
    if record is None or record.state is not PushState.PUSHED:
        return False
    if not pending:
        record.loaded.add(load)
        return False
    return load not in record.loaded


def drop(record: Record) -> None:
    if records.get(record.key) is record:
        del records[record.key]
