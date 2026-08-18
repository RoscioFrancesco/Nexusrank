import numpy as np
import pytest

from nexusrank.data import generate
from nexusrank.graph import HeteroGraph
from nexusrank.ppr import local_ppr, power_ppr, seed_vector
from nexusrank.store import Edge, Node, SQLiteStore


@pytest.fixture(scope="module")
def graph() -> HeteroGraph:
    store = SQLiteStore(":memory:")
    generate(store, n_people=60, seed=3)
    return HeteroGraph(store.nodes(), store.edges())


def test_transition_matrix_is_column_stochastic(graph):
    cols = np.asarray(graph.P.sum(axis=0)).ravel()
    nonzero = cols[cols > 0]
    assert np.allclose(nonzero, 1.0)


def test_edges_are_symmetric(graph):
    diff = abs(graph.A - graph.A.T)
    assert diff.nnz == 0 or diff.max() < 1e-12


def test_power_ppr_is_a_distribution_and_favours_seed(graph):
    seed = graph.index[graph.ids_of_type("person")[0]]
    r = power_ppr(graph.P, seed_vector(len(graph), {seed: 1.0}))
    assert r.min() >= -1e-12
    assert r.sum() == pytest.approx(1.0, abs=1e-6)
    assert r[seed] == max(r)


def test_local_and_power_ppr_agree_on_top_nodes(graph):
    seed = graph.index[graph.ids_of_type("skill")[0]]
    exact = power_ppr(graph.P, seed_vector(len(graph), {seed: 1.0}))
    approx = local_ppr(graph.P, {seed: 1.0}, eps=1e-9)
    assert np.abs(exact - approx).sum() < 0.02
    assert set(np.argsort(-exact)[:5]) & set(np.argsort(-approx)[:5])


def test_alpha_controls_locality():
    """Higher restart probability keeps more mass on the seed."""
    nodes = [Node(f"person:{i}", "person", f"P{i}") for i in range(6)]
    edges = [Edge(f"person:{i}", f"person:{i+1}", "KNOWS") for i in range(5)]
    g = HeteroGraph(nodes, edges)
    s = seed_vector(len(g), {g.index["person:0"]: 1.0})
    local = power_ppr(g.P, s, alpha=0.6)
    diffuse = power_ppr(g.P, s, alpha=0.05)
    assert local[g.index["person:0"]] > diffuse[g.index["person:0"]]
    assert diffuse[g.index["person:5"]] > local[g.index["person:5"]]


def test_explain_path_finds_shared_skill_chain():
    nodes = [Node("person:a", "person", "A"), Node("person:b", "person", "B"),
             Node("skill:rust", "skill", "Rust")]
    edges = [Edge("person:a", "skill:rust", "HAS_SKILL"),
             Edge("person:b", "skill:rust", "HAS_SKILL")]
    g = HeteroGraph(nodes, edges)
    path = g.explain_path({"person:a": 1.0}, "person:b")
    assert [h.dst for h in path] == ["skill:rust", "person:b"]
    assert [h.type for h in path] == ["HAS_SKILL", "HAS_SKILL"]


def test_unreachable_target_has_no_path():
    nodes = [Node("person:a", "person", "A"), Node("person:z", "person", "Z")]
    g = HeteroGraph(nodes, [])
    assert g.explain_path({"person:a": 1.0}, "person:z") == []
