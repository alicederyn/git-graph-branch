from git_graph_branch.git.object import GitObject

COMMIT_NO_PARENT = (
    b"commit 240\x00tree f5dcaf7e8cd5244bf0a46bdbbf8f139d3e9cb26a\n"
    b"author Alice Purcell <Alice.Purcell.39@gmail.com> 1648890856 +0100\n"
    b"committer Alice Purcell <Alice.Purcell.39@gmail.com> 1649018473 +0100\n"
    b"\nSkeleton project\n\nPrints out a list of current branches\n"
)
COMMIT_SINGLE_PARENT = (
    b"commit 259\x00tree 9f028a2d6b4dc0ab78d8f78d35e1cdbc98897218\n"
    b"parent 81ae0ae6c4457f6e5a4228e3fc4ec0a0ae41c033\n"
    b"author Alice Purcell <Alice.Purcell.39@gmail.com> 1649019785 +0100\n"
    b"committer Alice Purcell <Alice.Purcell.39@gmail.com> 1649019785 +0100\n"
    b"\nDetermine branch upstreams\n"
)
COMMIT_TWO_PARENTS = (
    b"commit 307\x00tree 09c854936c7dfa17fc746271490c5f396c0673e8\n"
    b"parent c4564522eaca107317787c09b65926d1428f09be\n"
    b"parent 1dc41a071c01a98c16dd02f9d8b64c18127100eb\n"
    b"author Alice Purcell <Alice.Purcell.39@gmail.com> 1649669026 +0100\n"
    b"committer Alice Purcell <Alice.Purcell.39@gmail.com> 1649669026 +0100\n"
    b"\nMerge branch 'a1' into a12\n"
)
COMMIT_COMMENT_SINGLE_LINE = COMMIT_SINGLE_PARENT
COMMIT_COMMENT_MULTILINE = (
    b"commit 359\x00tree bcf381c8a1bbaa867e91b8a3260a054ed87ccbd5\n"
    b"parent 1d773b6230135537f69f2fbf918ba55404a438f3\n"
    b"author Alice Purcell <Alice.Purcell.39@gmail.com> 1649529551 +0100\n"
    b"committer Alice Purcell <Alice.Purcell.39@gmail.com> 1649529551 +0100\n"
    b"\nAdd integration tests for upstream handling\n\n"
    b"Fix an issue this picked up with how git handles escapes when there are "
    b"no quotes\n"
)


def test_commit_no_parent() -> None:
    output = GitObject.decode(COMMIT_NO_PARENT)
    assert output.parents == ()
    assert output.first_parent is None


def test_commit_with_parent() -> None:
    output = GitObject.decode(COMMIT_SINGLE_PARENT)
    assert output.parents == ("81ae0ae6c4457f6e5a4228e3fc4ec0a0ae41c033",)
    assert output.first_parent == "81ae0ae6c4457f6e5a4228e3fc4ec0a0ae41c033"


def test_commit_two_parents() -> None:
    output = GitObject.decode(COMMIT_TWO_PARENTS)
    assert output.parents == (
        "c4564522eaca107317787c09b65926d1428f09be",
        "1dc41a071c01a98c16dd02f9d8b64c18127100eb",
    )
    assert output.first_parent == "c4564522eaca107317787c09b65926d1428f09be"


def test_comment_single_line() -> None:
    output = GitObject.decode(COMMIT_COMMENT_SINGLE_LINE)
    assert output.message == b"Determine branch upstreams\n"


def test_comment_multiline() -> None:
    output = GitObject.decode(COMMIT_COMMENT_MULTILINE)
    assert output.message == (
        b"Add integration tests for upstream handling\n\n"
        b"Fix an issue this picked up with how git handles "
        b"escapes when there are no quotes\n"
    )


def test_timestamp() -> None:
    output = GitObject.decode(COMMIT_NO_PARENT)
    assert output.timestamp == 1649018473
