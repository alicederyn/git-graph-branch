from asyncio import Event

from ._nixer import Nixer


class AsyncNixer(Nixer):
    def __init__(self) -> None:
        self._nixed = Event()

    def nix(self) -> None:
        self._nixed.set()

    @property
    def is_active(self) -> bool:
        return not self._nixed.is_set()

    async def wait_until_nixed(self) -> None:
        await self._nixed.wait()
