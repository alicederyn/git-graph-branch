# Proposed Fact API

```python
class Fact:
    """A dependency that nix tracks. It holds no data.

    The fact-finder keeps the data. A fact records which calculations
    depend on that data, so that they can be nixed when it changes, and
    so that the fact-finder can drop the data when nothing needs it.
    Never subclassed.
    """

    def record_use(self) -> None:
        """Make the calculation that is running depend on this fact.

        Allows a fact-finder to return the same fact multiple times.

        Raises NixError outside a report calculation, or if this fact is
        nixed or moot.
        """

    def nix(self) -> None:
        """Nix this fact and each calculation that depends on it.

        Raises NixError during a report calculation: use when_safe_to_nix.
        """

    # Register cleanup logic
    # Callback registration is chainable (fact.on_nix(fact.on_moot(self.delete, key)))
    # A callback will be executed at most once.
    # A callback registered after an event has occurred runs immediately.
    # In this version of the API, moot is final.
    def on_nix(self, callback, /, *args, **kwargs) -> callback: ...
    def on_moot(self, callback, /, *args, **kwargs) -> callback: ...

    nixed: bool  # read-only property
    moot: bool  # read-only property

    @contextmanager
    def calculation(self) -> Iterator[None]:
        """Tracks what facts this fact's calculation depends on.

        If a fact calculation is already ongoing, a dependency will be added on this fact.

        The active fact is tracked via context variables. If a fact calculation exits,
        the context variable is marked dead; all tasks run to compute this fact MUST
        have returned before that happens. Any attempt to add a new dependency to this
        fact in such a task will raise an error.

        If the body depended on no nixable fact, the fact is constant: nothing
        records a dependency on it, and it never goes moot.
        """


# Background task API
def run_background_task(coro) -> None:
    """Start a background task to track external fact changes.

    Fact finders that return external facts (e.g. file contents, API query results)
    should start a background task to track when those facts are invalidated.

    Background tasks must not create new facts. They may nix existing facts, and
    they may update shared storage for subsequent fact calculation to use.
    Both of these must be done via `when_safe_to_nix`. Direct use of any nix API
    other than `when_safe_to_nix` in a background task will raise an error.

    When computing a one-shot report, this function will be a no-op.
    """


def when_safe_to_nix(callback, /, *args, **kwargs) -> None:
    """Run *callback* once no active report calculation is in progress.

    Background tasks must not nix existing facts directly. Background tasks
    must not update shared storage directly. They must use this function to
    wait until it is safe.

    The callback may create facts, but must not start a calculation. An
    error will be raised if it tries. Facts created during a callback will
    not be marked moot until all recalculations triggered by callback nixes
    are done.
    """
```

