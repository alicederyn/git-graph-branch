from git_graph_branch.git.bloom import Bloom

# Some random hashes grabbed from a project
HASHES = (
    bytes.fromhex("460ca587c0f9cffa9d3dc5ed4b8d8dbe16356f80"),
    bytes.fromhex("10c865f91a52f9d5f501874e670b39886ecca717"),
    bytes.fromhex("eaec546bb5ef92c94f35f3c64d540b37147c13ac"),
    bytes.fromhex("41147ae7baae5dfc875a3cf9680ca14b8ef1ca83"),
    bytes.fromhex("d7a240f058484aa38861638b484df4b0a04ac427"),
    bytes.fromhex("1e3ce77d3c98e24c1b1fdfa8ff8312ec9a83da04"),
    bytes.fromhex("124516a0a10374af2776bec38ab5a93b7c4053af"),
    bytes.fromhex("19e6eddf9294a228a360c349bd11c9c3a496371d"),
    bytes.fromhex("2bde091197c9ae0071e6a7192a370863d99b8aad"),
    bytes.fromhex("a438975ff41c761d32493057984ea8acfe98a546"),
    bytes.fromhex("bee9a66a03c2627dbdbdd239a3800a61c777ed8f"),
    bytes.fromhex("32a0dc0b4d630fcdc8c3d2795c344bab5766b262"),
    bytes.fromhex("c3435e94b5b0096613786c03fdf713e04c30bb06"),
    bytes.fromhex("384f218b194f59a7eba5ff07414bfa728ba629d9"),
    bytes.fromhex("08c797dc65e357d647b9f68eb9c6be4d4867bf7b"),
    bytes.fromhex("75a89e78e7598ffb5db7e043fe17a7c0442f84ce"),
    bytes.fromhex("af565afab5e5108f6cfacda547c1f76bb11e778f"),
    bytes.fromhex("8ba7c410b47f95095557c46a2fd3c67acca32672"),
    bytes.fromhex("1bbb4caee6da676fa0302b84b2b6fceccef604da"),
    bytes.fromhex("abd900b506a4f8b1ea49e9bf4ebd64403332f2a9"),
    bytes.fromhex("8e47a2a0698c2983300fe470a9dbd58c53cbc0df"),
    bytes.fromhex("1a14cc726df777c317ac7d6257c11fc40d4a134d"),
    bytes.fromhex("cfe33fb0d1cc14d37574f416cc2a1c2328faa4e0"),
    bytes.fromhex("8af4ddb3ff4760e7e748c70fd7c761304320de6d"),
    bytes.fromhex("f25aed5a8a373f27bec4f8240aa216e2138b09e4"),
    bytes.fromhex("af38201a32ba05d2da767f2ffe3019bcace38ff3"),
    bytes.fromhex("cf2e31d83d5af9a4d343ab0c84d556c00165456a"),
    bytes.fromhex("819a14ca02b6e9551c71801a13a0b0fc0951a4e2"),
    bytes.fromhex("5996cc18b0017b44f803115a0621e772072195e5"),
    bytes.fromhex("6dac8b229fd1ea3fe5fcc5a8e5d8af993322f474"),
    bytes.fromhex("ca5c2389a19b873647da8654f84cb66329ddcca6"),
    bytes.fromhex("00ea78cd61f719163553c267d9ea3c7fba5fbb8b"),
    bytes.fromhex("194128049e1b564ad4c0fbd29f439f56dd2df6a2"),
    bytes.fromhex("cd5e3c1e6ecf707a2ef0289f669c3f57e7f28e74"),
    bytes.fromhex("ab055a46309df3e01d2bf257b3dda48c735848a5"),
    bytes.fromhex("7ebef966486e40fe397edb4a49b232bb00c42b28"),
    bytes.fromhex("fe7c45f4bbad903f04be27962545b48d3002bc4c"),
    bytes.fromhex("6453cd22822e45fe985c4b68b5a9a9c39a2013b3"),
    bytes.fromhex("dcf40a63b2fd9099b4c2df13996883f059370a4a"),
    bytes.fromhex("f2cbb4f0ae1bf7a55da7f46362ecb95f4db7d1ce"),
)


def test_empty_bloom() -> None:
    bloom = Bloom(10)
    assert len(bloom._data) == 18  # 1.44 bits per item per hash = 144 bits = 18 bytes
    assert not any(h in bloom for h in HASHES)


def test_small_sparse_bloom() -> None:
    bloom = Bloom(10)
    bloom.add(HASHES[0])
    assert HASHES[0] in bloom
    assert not any(h in bloom for h in HASHES[1:])


def test_small_filled_bloom() -> None:
    bloom = Bloom(10)
    for h in HASHES[:10]:
        bloom.add(h)
    assert all(h in bloom for h in HASHES[:10])
    assert not any(h in bloom for h in HASHES[10:])
