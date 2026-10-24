import pytest
from graphql import build_schema, parse, validate

from git_graph_branch.github.merge import Query, QueryError, merge

SCHEMA = build_schema("""
    type Query {
      repository(owner: String!, name: String!): Repository
      viewer: User!
    }
    type Repository { name: String! owner: User! }
    type User { login: String! }
""")

REPO_QUERY = Query(
    """
    query ($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) { ...Repo }
    }
    fragment Repo on Repository { name owner { login } }
    """,
    {"owner": "alice", "name": "one"},
)


def test_merge_renames_variables_and_fragments_of_each_query() -> None:
    other = Query(REPO_QUERY.document, {"owner": "bob", "name": "two"})

    merged = merge([REPO_QUERY, other])

    assert validate(SCHEMA, parse(merged.document)) == []
    assert merged.variables == {
        "q0_owner": "alice",
        "q0_name": "one",
        "q1_owner": "bob",
        "q1_name": "two",
    }
    assert "q0_repository: repository(owner: $q0_owner" in merged.document
    assert "fragment q1_Repo on Repository" in merged.document


def test_merge_keeps_existing_aliases_as_response_keys() -> None:
    query = Query("{ me: viewer { login } }", {})

    merged = merge([query])

    assert merged.split({"data": {"q0_me": {"login": "alice"}}}) == [
        {"me": {"login": "alice"}}
    ]


def test_merge_rejects_mutations() -> None:
    with pytest.raises(ValueError):
        merge([Query("mutation { viewer { login } }", {})])


def test_split_gives_each_query_its_own_data() -> None:
    viewer = Query("{ viewer { login } }", {})
    merged = merge([REPO_QUERY, viewer])

    results = merged.split(
        {
            "data": {
                "q0_repository": {"name": "one"},
                "q1_viewer": {"login": "alice"},
            }
        }
    )

    assert results == [{"repository": {"name": "one"}}, {"viewer": {"login": "alice"}}]


def test_split_gives_an_error_to_the_query_in_its_path() -> None:
    viewer = Query("{ viewer { login } }", {})
    merged = merge([REPO_QUERY, viewer])

    results = merged.split(
        {
            "data": {"q0_repository": None, "q1_viewer": {"login": "alice"}},
            "errors": [
                {"message": "Not found", "path": ["q0_repository"], "type": "NOT_FOUND"}
            ],
        }
    )

    error = results[0]
    assert isinstance(error, QueryError)
    assert error.errors == [
        {"message": "Not found", "path": ["repository"], "type": "NOT_FOUND"}
    ]
    assert results[1] == {"viewer": {"login": "alice"}}


@pytest.mark.parametrize(
    "response",
    [
        {"data": None, "errors": [{"message": "Bad", "path": ["q0_viewer"]}]},
        {"data": {"q0_viewer": None}, "errors": [{"message": "Invalid query"}]},
    ],
    ids=["null data", "error without path"],
)
def test_split_fails_all_queries(response: dict[str, object]) -> None:
    merged = merge([Query("{ viewer { login } }", {}), REPO_QUERY])

    results = merged.split(response)

    assert all(isinstance(result, QueryError) for result in results)
