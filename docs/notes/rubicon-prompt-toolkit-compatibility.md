# Can prompt_toolkit run on Rubicon's CFEventLoop?

Supporting evidence for [ADR 1](../adr/0001-prompt-toolkit-for-mouse-support.md).

Findings from reading `rubicon-objc` 0.5.6, `prompt_toolkit` 3.0.53 and Apple's
`CFSocket.c`. All of it is source reading; none of it was observed on macOS.

## Conclusion

Yes, with no blocking incompatibility found.

## prompt_toolkit does not want to own the loop

`Application.run_async()` is `async def` and takes the loop from
`get_running_loop()`. Only the synchronous `run()` calls `asyncio.run`.

The loop methods it touches are `add_reader`, `remove_reader`,
`add_signal_handler`, `remove_signal_handler`, `create_future`, `create_task`,
`call_soon_threadsafe`, `get/set_exception_handler`, `run_in_executor`,
`is_closed` and `slow_callback_duration`. All are present on `CFEventLoop`,
which subclasses `unix_events.SelectorEventLoop`.

## A tty fd is safe with `CFSocketCreateWithNative`

`CFEventLoop.add_reader` registers the fd via `CFSocketCreateWithNative` plus a
CFRunLoop source (`rubicon/objc/eventloop.py:375-453`), a direct port of
Twisted's `cfreactor._watchFD`. The concern was that CFSocket is documented for
BSD sockets, whereas stdin is a character device.

The shipping CoreFoundation implementation is the legacy one
(`#define NEW_SOCKET 0`, `CFSocket.c:29`). That path never inspects the fd type:
a failing `getsockopt(SO_TYPE)` just leaves `_socketType = 0`
(`CFSocket.c:2444`), the manager thread polls with `select()`
(`CFSocket.c:2151`), and `__CFNativeSocketIsValid` tests `fcntl(F_GETFL)` for
`EBADF` rather than socket-ness (`CFSocket.c:1206`). For `kCFSocketReadCallBack`
— the type rubicon requests — the handler only signals readability and never
calls `recv`.

The disabled `NEW_SOCKET` branch explicitly whitelists `S_IFCHR` and `S_IFIFO`
(`CFSocket.c:245`), confirming ttys and pipes are intended to work.

## fd 0 is not closed on detach

`CFSocketInvalidate` closes the fd only when `kCFSocketCloseOnInvalidate` (128)
is set, and rubicon's `CFSocketSetSocketFlags(1|8)` clears it
(`eventloop.py:306`). Re-adding a reader after removal is clean because
invalidation removes the fd from `__CFAllSockets`.

## Signals work

`CFEventLoop` does not override `add_signal_handler`. The inherited Unix
implementation needs only the socketpair self-pipe, which `_make_self_pipe`
registers through rubicon's own `_add_reader`. SIGWINCH-driven resize is
therefore available.

## Duplicate read notifications are already handled

Twisted documents CFSocket delivering spurious read callbacks
(`cfreactor.py:189`) and rubicon carries the same comment. On a blocking tty
that would stall the loop in `os.read`. prompt_toolkit guards it with a
zero-timeout `select.select` before reading (`input/posix_utils.py`).

## The global `functools` patch is not a problem

`nix.install()` patches `functools.lru_cache` — and thereby `functools.cache`,
which resolves `lru_cache` as a module global at call time — so every cached
call registers a `cache_clear` with the active cohort. prompt_toolkit uses zero
`functools.lru_cache`; it has its own `SimpleCache` and `FastDictCache`.

## Known leak

`CFSocketHandle.cancel()` calls `CFSocketInvalidate` but never `CFRelease`s the
CFSocket, leaking one per attach/detach cycle. Cosmetic unless readers are
cycled frequently.
