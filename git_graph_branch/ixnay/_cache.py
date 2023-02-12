from enum import Enum
from typing import Callable, Generic, Literal, TypeVar
from weakref import WeakSet, ref

from ._nixer import Nixer

T = TypeVar("T")


class _NoValue(Enum):
    NO_VALUE = 0


class _NixableCachedCallable(Generic[T]):
    def __init__(self, callable: Callable[[Nixer], T]) -> None:
        self._callable = callable
        self._cached_result: T | Literal[_NoValue.NO_VALUE] = _NoValue.NO_VALUE
        self._inactive_nixer: ref[Nixer] | None = None
        self._nix_registered = False
        self._active_nixers = WeakSet[Nixer]()

    def __call__(self, nixer: Nixer) -> T:
        if self._inactive_nixer and self._inactive_nixer() is not nixer:
            self._inactive_nixer = None
            if not self._nix_registered:
                self._cached_result = _NoValue.NO_VALUE

        if nixer.is_active:
            if self._cached_result is _NoValue.NO_VALUE:
                self._cached_result = self._callable(self)
                self._active_nixers.add(nixer)
                self._nix_registered = True
        else:
            if self._inactive_nixer:
                assert self._inactive_nixer() is nixer
                assert self._cached_result is not _NoValue.NO_VALUE
            else:
                self._inactive_nixer = ref(nixer)
                if not self._nix_registered:
                    self._cached_result = _NoValue.NO_VALUE
                    self._cached_result = self._callable(nixer)
                else:
                    assert self._cached_result is not _NoValue.NO_VALUE
        return self._cached_result

    def nix(self) -> None:
        if not self._inactive_nixer or self._inactive_nixer() is None:
            self._cached_result = _NoValue.NO_VALUE
            self._inactive_nixer = None
        nixers = list(self._active_nixers)
        self._active_nixers.clear()
        self._nix_registered = False
        for nixer in nixers:
            nixer.nix()

    @property
    def is_active(self) -> bool:
        return True

    def clear(self) -> None:
        nixers = list(self._active_nixers)
        self._cached_result = _NoValue.NO_VALUE
        self._inactive_nixer = None
        self._nix_registered = False
        self._active_nixers.clear()
        for nixer in nixers:
            nixer.nix()


def cache(__fn: Callable[[Nixer], T]) -> _NixableCachedCallable[T]:
    return _NixableCachedCallable(__fn)
