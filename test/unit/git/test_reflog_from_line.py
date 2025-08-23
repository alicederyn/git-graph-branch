from git_graph_branch.git.commit import Commit
from git_graph_branch.git.reflog import ReflogEntry, reflog_from_line


def test_real_entry() -> None:
    line = (
        "4772051169d64bd03e73880caba2d948326b6123 "
        "d91365a2b659f8dbc6e8f5629999932a7128e730 "
        "Unit Test Runner <unit-test-runner@example.com> "
        "1755954543 +0100 "
        " commit: Commit 13"
    )

    result = reflog_from_line(line)

    assert result == ReflogEntry(
        Commit("d91365a2b659f8dbc6e8f5629999932a7128e730"), 1755954543
    )
