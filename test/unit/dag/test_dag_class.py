from git_graph_branch.dag import DAG


def test_insert_node() -> None:
    g: DAG[str] = DAG()
    assert ("a", "b") not in g

    assert g.add(("a", "b"))
    assert ("a", "b") in g


def test_cannot_insert_self_edge() -> None:
    g: DAG[str] = DAG()

    assert not g.add(("a", "a"))
    assert ("a", "a") not in g


def test_downstream() -> None:
    g: DAG[str] = DAG()
    g.add(("b", "c"))
    g.add(("a", "b"))
    g.add(("c", "d"))
    g.add(("b", "e"))

    assert g._downstream["a"] == {"a", "b", "c", "d", "e"}


def test_upstream() -> None:
    g: DAG[str] = DAG()
    g.add(("b", "c"))
    g.add(("a", "b"))
    g.add(("c", "d"))
    g.add(("b", "e"))

    assert g._upstream["d"] == {"a", "b", "c", "d"}


def test_cycle_ignored() -> None:
    g: DAG[str] = DAG()
    assert g.add(("b", "c"))
    assert g.add(("a", "b"))
    assert g.add(("c", "d"))

    assert not g.add(("d", "a"))
    assert ("d", "a") not in g


def test_repr() -> None:
    assert repr(DAG()) == "DAG()"

    g = DAG(edges=[("a", "b"), ("b", "c"), ("a", "d")])
    assert repr(g) == "DAG([('a','b'), ('a','d'), ('b','c')])"


def test_eq() -> None:
    g1 = DAG(edges=[("a", "b"), ("b", "c"), ("a", "d")])
    g2 = DAG(edges=[("b", "c"), ("a", "b"), ("a", "d")])
    g3: DAG[str] = DAG()

    assert g1 == g1
    assert g1 == g2
    assert g1 != g3
