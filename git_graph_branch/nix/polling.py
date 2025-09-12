from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .cohort import Cohort, on_add_cohort

SAFETY_MARGIN = timedelta(seconds=1)
cohort_timestamps: dict[Cohort, float] = {}

# Capture Path methods before we patch them
PATH_STAT = Path.stat


def add_cohort(cohort: Cohort) -> None:
    if cohort in cohort_timestamps:
        raise RuntimeError("Cannot register cohort twice")
    timestamp = (datetime.now(UTC) - SAFETY_MARGIN).timestamp()
    cohort_timestamps[cohort] = timestamp
    cohort.on_nix.append(lambda: cohort_timestamps.pop(cohort))


on_add_cohort.append(add_cohort)


def paths_in_cohort(cohort: Cohort) -> Iterator[Path]:
    yield from cohort.paths
    seen: set[Path] = set()  # Avoid processing the same path twice
    for glob in cohort.globs:
        for path in glob.base_path.glob(glob.pattern):
            if path not in cohort.paths and path not in seen:
                seen.add(path)
                yield path


def should_nix(cohort: Cohort, timestamp: float) -> bool:
    unseen = cohort.seen.copy()

    for path in paths_in_cohort(cohort):
        try:
            stat = PATH_STAT(path)
            unseen.discard(path)
            if stat.st_mtime >= timestamp:
                # Created or modified
                return True
        except FileNotFoundError:
            pass

    # Any deleted?
    return bool(unseen)


def nix_cohorts_with_changes() -> None:
    to_nix = [
        cohort
        for cohort, timestamp in cohort_timestamps.items()
        if should_nix(cohort, timestamp)
    ]
    for cohort in to_nix:
        cohort.nix()
