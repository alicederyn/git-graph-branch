from git_graph_branch.dag import sanitized_parents


def test_extra_parent_nodes_removed() -> None:
    result = sanitized_parents([1, 2, 3, 4], lambda i: [i + 1, i + 2])

    assert result == {1: {2, 3}, 2: {3, 4}, 3: {4}, 4: set()}
