# nix facts

The vocabulary for the dependency graph of
[ADR 2](../adr/0002-fine-grained-invalidation-and-release-in-nix.md).

**Facts.** A fact is a set of information held in memory, such as the content of
a file (a "file state fact"), or the result of a GraphQL query, with a shared
lifetime managed by nix.

**Dependencies.** If fact A is calculated using fact B, fact A depends on fact
B. Only direct dependencies are recorded. Calculating one fact can trigger the
calculation of another, for example on a cache miss. A cache entry fact may
depend on other facts. A file state fact will not depend on other facts.

**Nixing.** A fact may be nixed. It must be discarded, and all facts dependent
on it must be nixed, before facts are recalculated.

**Fact-finders.** A fact-finder is responsible for determining facts. It may
also directly nix them; for example, a file state fact can be nixed by its
fact-finder when the file changes. A fact-finder can return an existing fact,
creating a DAG of dependencies. (Cycles are not permitted.)

**The report.** The report is the fact that contains the state of the world, as
far as the tool needs to know it to show the user what it shows. The UI renders
the current report. When the current report is nixed, nix starts to calculate a
new report. When that calculation is complete, the new report replaces the
current report.

**Mootness.** A fact is moot if neither the current report nor the new report
depends on it, directly or transitively. A fact-finder that holds references to
facts should register to be informed when they are no longer depended upon. It
may choose to keep moot facts for optimization reasons, but if it does not it
should clean up all associated data.
