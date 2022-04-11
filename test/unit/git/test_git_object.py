from git_graph_branch.git.object import GitObject

COMMIT_NO_PARENT = bytes.fromhex(
    "7801958d410e823010003df7157b3721050ab48931fa03125fd02e5ba9166aca"
    "f6ff12c3073cce1c66302d4b6068943c712602df4d68fd401aa7ae51ca796955"
    "ef26e7bcf6756ba6960cbaa6b7c2169e53867b0c4830968c14235c7e581d58b5"
    "e6f65c6c8815a6e50a75afb43652773d9c652da5d8edfe66fab76264add5d01e"
    "15f17853244e2b7c727a11b210630e2b6f900a8385183686e4014bceb432b86c"
    "579c69135f12b75030"
)
COMMIT_SINGLE_PARENT = bytes.fromhex(
    "7801a54f5b0ac24010f37b4f31ff42d9673b0b220a1ec02b4ca7532d74dbb2dd"
    "dedf45bc813f81242424bca63415b0219e4a1681386a8b6487b6f7036bea3b1c"
    "70ace082181e7a8e88b1b306d54659960268483449cbde876e6c2590b716c58d"
    "eca5e6abe50d6be7141de5bd66b8cf130b3c8fcc32cf70f9d2e6471b176faf44"
    "d3dcf09aae605a1fb5891d06386ba3b5aa6add5ae4bf16f5905a91a645a0cfb4"
    "f01b8e6dafdf29edea035098530b"
)
COMMIT_TWO_PARENTS = bytes.fromhex(
    "7801a58f4b6a04310c44b3ee5368378bc020d96ed982109203047205b5ac9e69"
    "e84f309efba709c909b27c45f18ab263db960e11f3536fee8062654c12d9729d"
    "95f26c3971c894046d9ca3b021e7e865f8d2e67b074b23a731045753c21c29e7"
    "920d65e25102574aa1cc27f95f9faa2552cc64482ac5886bc5304b2d1327a342"
    "e716a24f833efafd68f0be2ee6f0f968e6eb0a2f3f78fdc56b94b7dba6cb7ab5"
    "637b05e224cc8281e1194fc970a6e7b7eeffb30c1fde6e0e53d3ddee7051bac0"
    "b2f70394c2f00de3525c78"
)
COMMIT_COMMENT_SINGLE_LINE = COMMIT_SINGLE_PARENT
COMMIT_COMMENT_MULTILINE = bytes.fromhex(
    "7801a590416ec4200c45bbe614de571a41080948a3aab3e9ba573060026a0269"
    "204a8f5f34ea0dbab2bef5fdfdf55cd9b6d4402af3d20e22b02e482d9c46612d"
    "a29e6632c26a94c3c491ab91bc9e9db35eb11d0fca0d849f6769a74172219592"
    "73984c18820d46688b4a8d7cc451ea20199e2d96031e6b72049fe7e1685de1fe"
    "94b73f7993e67dd930ad3757b63710d368d4609412f0ca05e7ac6f7bd746ff4b"
    "610fef21e546cb812d950c8d6aab107ab973af1d026e1031fb35e585b18ff403"
    "9821d57a12b4982aecc97d91ef5eb8528b10cb054b27f83ca10a541dee7d5e91"
    "7a74a483a093825ce0fb2cfd15fb053918766f"
)


def test_commit_no_parent() -> None:
    output = GitObject.decode([COMMIT_NO_PARENT])
    assert output.parents == ()
    assert output.first_parent is None


def test_commit_with_parent() -> None:
    output = GitObject.decode([COMMIT_SINGLE_PARENT])
    assert output.parents == ("81ae0ae6c4457f6e5a4228e3fc4ec0a0ae41c033",)
    assert output.first_parent == "81ae0ae6c4457f6e5a4228e3fc4ec0a0ae41c033"


def test_commit_two_parents() -> None:
    output = GitObject.decode([COMMIT_TWO_PARENTS])
    assert output.parents == (
        "c4564522eaca107317787c09b65926d1428f09be",
        "1dc41a071c01a98c16dd02f9d8b64c18127100eb",
    )
    assert output.first_parent == "c4564522eaca107317787c09b65926d1428f09be"


def test_comment_single_line() -> None:
    output = GitObject.decode([COMMIT_COMMENT_SINGLE_LINE])
    assert output.message == b"Determine branch upstreams\n"


def test_comment_multiline() -> None:
    output = GitObject.decode([COMMIT_COMMENT_MULTILINE])
    assert output.message == (
        b"Add integration tests for upstream handling\n\n"
        b"Fix an issue this picked up with how git handles "
        b"escapes when there are no quotes\n"
    )
