import pytest
from fastapi.testclient import TestClient

from nexusrank.data import CLUSTERS, generate
from nexusrank.engine import NexusRank
from nexusrank.lexical import BM25Index
from nexusrank.store import Node, SQLiteStore


@pytest.fixture(scope="module")
def engine() -> NexusRank:
    store = SQLiteStore(":memory:")
    generate(store, n_people=120, seed=11)
    return NexusRank(store)


def test_store_roundtrip():
    store = SQLiteStore(":memory:")
    assert store.is_empty()
    generate(store, n_people=20, seed=1)
    assert not store.is_empty()
    assert len(store.nodes()) > 20 and len(store.edges()) > 40


def test_bm25_ranks_exact_match_first():
    nodes = [Node("a", "person", "Ada", "Rust systems engineer"),
             Node("b", "person", "Bo", "product designer"),
             Node("c", "skill", "Rust", "Rust language")]
    hits = BM25Index(nodes).search("rust")
    assert hits[0][0] in {"c", "a"}
    assert {h[0] for h in hits} == {"a", "c"}


def test_seeds_include_concept_nodes(engine):
    seeds = engine.seeds_for("kubernetes distributed systems")
    types = {engine.graph.by_id[s].type for s in seeds}
    assert "skill" in types


def test_ranking_returns_cluster_relevant_people(engine):
    resp = engine.rank("graph neural networks recommender systems", limit=8)
    assert len(resp.results) == 8
    ml_terms = set(CLUSTERS["ml"]["skills"]) | set(CLUSTERS["ml"]["companies"])
    relevant = sum(any(t.lower() in engine.graph.by_id[r.id].text.lower()
                       for t in ml_terms) for r in resp.results)
    assert relevant >= 6
    assert resp.results == sorted(resp.results, key=lambda r: -r.score)


def test_graph_signal_changes_the_ranking(engine):
    lexical_only = engine.rank("kubernetes", limit=5, graph_weight=0.0)
    graph_only = engine.rank("kubernetes", limit=5, graph_weight=1.0)
    assert [r.id for r in lexical_only.results] != [r.id for r in graph_only.results]
    assert all(r.lexical_score > 0 for r in lexical_only.results)


def test_every_result_carries_an_explanation(engine):
    resp = engine.rank("payments risk modeling", limit=6)
    for r in resp.results:
        assert r.why
        for hop in r.path:
            assert hop["src"] in engine.graph.index
            assert hop["dst"] in engine.graph.index
        if r.path:
            assert r.path[-1]["dst"] == r.id


def test_seed_people_are_explained_from_other_seeds(engine):
    """A person who matched the query lexically still needs actionable evidence."""
    resp = engine.rank("user research design systems", limit=5)
    seed_ids = {s["id"] for s in resp.seeds}
    seed_results = [r for r in resp.results if r.id in seed_ids]
    assert seed_results, "expected at least one lexical seed in the top results"
    for r in seed_results:
        assert r.path and r.path[0]["src"] != r.id
        assert r.why != "Query seed."


def test_viewer_biases_results_toward_their_neighbourhood(engine):
    viewer = engine.graph.ids_of_type("person")[0]
    plain = {r.id for r in engine.rank("engineer", limit=10).results}
    with_viewer = engine.rank("engineer", viewer=viewer, limit=10).results
    assert viewer not in {r.id for r in with_viewer}
    assert {r.id for r in with_viewer} != plain


def test_solvers_produce_similar_top_results(engine):
    a = [r.id for r in engine.rank("genomics", limit=5, solver="local").results]
    b = [r.id for r in engine.rank("genomics", limit=5, solver="power").results]
    assert len(set(a) & set(b)) >= 3


def test_subgraph_is_connected_and_small(engine):
    sub = engine.subgraph("design systems user research", people=12)
    ids = {n["id"] for n in sub["nodes"]}
    assert 12 <= len(ids) <= 120
    assert sub["edges"]
    for e in sub["edges"]:
        assert e["source"] in ids and e["target"] in ids


def test_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUSRANK_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("NEXUSRANK_PEOPLE", "40")
    import importlib

    import nexusrank.api as api
    api = importlib.reload(api)
    client = TestClient(api.app)
    assert client.get("/api/health").json()["nodes"] > 40
    body = client.get("/api/search", params={"q": "rust kubernetes"}).json()
    assert body["results"] and body["seeds"]
    g = client.get("/api/graph", params={"q": "rust", "people": 8}).json()
    assert g["nodes"] and g["edges"]
    assert client.get("/api/node/does-not-exist").status_code == 404
    assert client.get("/api/viewers").json()["viewers"]
