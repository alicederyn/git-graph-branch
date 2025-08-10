import asyncio
from collections.abc import Collection, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .cohort import Cohort

SAFETY_MARGIN = timedelta(seconds=1)

# Capture Path methods before we patch them
PATH_STAT = Path.stat


def paths_in_cohort(cohort: Cohort) -> Iterator[Path]:
    yield from cohort.paths
    seen: set[Path] = set()  # Avoid processing the same path twice
    for glob in cohort.globs:
        for path in glob.base_path.glob(glob.pattern):
            if path not in cohort.paths and path not in seen:
                seen.add(path)
                yield path


def should_nix(cohort: Cohort, should_be_seen: set[Path], last_check: datetime) -> bool:
    unseen = should_be_seen.copy()

    for path in paths_in_cohort(cohort):
        try:
            stat = PATH_STAT(path)
            unseen.discard(path)
            if stat.st_mtime >= last_check.timestamp():
                # Created or modified
                return True
        except FileNotFoundError:
            pass

    return bool(unseen)


class PollingNixer:
    def __init__(self, poll_every: timedelta) -> None:
        self._poll_every = poll_every
        self._last_check = datetime.now(UTC) - SAFETY_MARGIN
        self._seen: dict[Cohort, set[Path]] = {}

    def add_cohort(self, cohort: Cohort) -> None:
        self._seen.setdefault(cohort, set())

    @property
    def cohorts(self) -> Collection[Cohort]:
        return self._seen.keys()

    def remove_cohort(self, cohort: Cohort) -> None:
        self._seen.pop(cohort, None)

    def path_seen(self, cohort: Cohort, path: Path) -> None:
        self._seen[cohort].add(path)

    def poll(self) -> None:
        start_time = datetime.now(UTC) - SAFETY_MARGIN
        for cohort, paths in list(self._seen.items()):
            if should_nix(cohort, paths, self._last_check):
                self._seen.pop(cohort)
                for invalidate_cache in cohort.invalidate_caches:
                    invalidate_cache()
                cohort.nix()
        self._last_check = start_time

    async def poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_every.total_seconds())
            self.poll()
