import numpy as np
import pytest

from nexusrank import enrichment
from nexusrank.data import generate
from nexusrank.engine import NexusRank
from nexusrank.ppr import local_ppr
from nexusrank.store import SQLiteStore

MARIO = {
    "name": "Mario Rossi",
    "linkedin_url": "https://www.linkedin.com/in/mario",
    "company": "Jane Street",
    "position": "Quant Intern",
    "location": "Milan",
    "notes": "met at a workshop",
    "sections": {
        "education": [{"institution": "EPFL", "degree": "MSc Computational Science",
                       "field": "Numerical Methods", "start_year": "2023",
                       "end_year": "2025"}],
        "experience": [{"organization": "Jane Street", "title": "Quant Intern",
                        "start": "2025", "end": ""}],
        "skills": [{"name": "Numerical Linear Algebra"}],
        "activities": [{"organization": "EPFL Robotics Club", "role": "Treasurer"}],
        "projects": [{"title": "Sparse Solver Benchmarks",
                      "description": "Comparing Krylov methods"}],
    },
}


@pytest.fixture()
def store() -> SQLiteStore:
    s = SQLiteStore(":memory:")
    generate(s, n_people=40, seed=5)
    enrichment.ensure_tables(s)
    return s


@pytest.fixture()
def mario(store) -> str:
    return enrichment.add_person(store, MARIO)["id"]


def test_fresh_install_has_no_contacts(tmp_path, monkeypatch):
    """First launch has demo data, while My Network remains empty."""
    monkeypatch.setenv("NEXUSRANK_DB", str(tmp_path / "fresh.db"))
    monkeypatch.delenv("NEXUSRANK_DEMO", raising=False)
    import importlib

    from fastapi.testclient import TestClient

    import nexusrank.api as api
    api = importlib.reload(api)
    client = TestClient(api.app)
    client.headers.update({
        "X-NexusRank-Token": client.get("/api/client-token").json()["token"]
    })
    h = client.get("/api/health").json()
    assert h["nodes"] > 0 and h["edges"] > 0 and h["my_network"] == 0
    assert client.get("/api/suggestions").json()["suggestions"]
    assert client.get("/api/search", params={"q": "quantum mechanics"}).json()["results"]
    assert client.get("/api/viewers").json()["viewers"]
    added = client.post("/api/person", json={"name": "Mario Rossi",
                                             "sections": MARIO["sections"]}).json()
    hits = client.get("/api/search", params={"q": "EPFL"}).json()["results"]
    assert [h["id"] for h in hits] == [added["id"]]


def test_startup_repairs_empty_my_preference_and_seeds_demo(tmp_path, monkeypatch):
    db = tmp_path / "stale.db"
    s = SQLiteStore(str(db))
    enrichment.ensure_tables(s)
    enrichment.set_pref(s, "active_dataset", "my")
    monkeypatch.setenv("NEXUSRANK_DB", str(db))
    import importlib

    from fastapi.testclient import TestClient

    import nexusrank.api as api
    api = importlib.reload(api)
    client = TestClient(api.app)
    client.headers.update({
        "X-NexusRank-Token": client.get("/api/client-token").json()["token"]
    })
    h = client.get("/api/health").json()
    assert h["active_dataset"] == "demo"
    assert h["nodes"] > 0
    assert client.get("/api/search", params={"q": "quantum mechanics"}).json()["results"]


def test_enrichment_persists(store, mario):
    prof = enrichment.get_profile(store, mario)
    assert prof["manual"] is True and prof["enriched"] is True
    assert prof["source_type"] == "manual"
    assert prof["source_url"] == MARIO["linkedin_url"]
    assert prof["updated_at"]
    assert prof["sections"]["education"][0]["institution"] == "EPFL"
    assert prof["location"] == "Milan" and prof["notes"] == "met at a workshop"


def test_duplicate_institution_is_reused(store, mario):
    other = enrichment.add_person(store, {
        "name": "Ada Bianchi",
        "sections": {"education": [{"institution": "EPFL", "degree": "BSc",
                                    "field": "Numerical Methods"}]},
    })["id"]
    rows = store.conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE id='school:my:epfl'").fetchone()[0]
    assert rows == 1
    dsts = {r[0] for r in store.conn.execute(
        "SELECT dst FROM edges WHERE src=? AND type='STUDIED_AT'", (other,))}
    assert "school:my:epfl" in dsts


def test_graph_relations_created(store, mario):
    rels = dict(store.conn.execute(
        "SELECT type, dst FROM edges WHERE src=?", (mario,)).fetchall())
    assert rels["STUDIED_AT"] == "school:my:epfl"
    assert rels["DEGREE_FIELD"] == "field:my:numerical-methods"
    assert rels["WORKED_AT"] == "company:my:jane-street"
    assert rels["SKILLED_IN"] == "skill:my:numerical-linear-algebra"
    assert rels["MEMBER_OF"] == "activity:my:epfl-robotics-club"
    assert rels["WORKED_ON"] == "project:my:sparse-solver-benchmarks"


def test_bm25_sees_new_education_and_skills(store, mario):
    engine = NexusRank(store)
    hits = dict(engine.lex.search("EPFL computational science"))
    assert mario in hits and hits[mario] > 0
    ranked = [r.id for r in engine.rank("EPFL computational science", limit=5).results]
    assert mario in ranked
    assert mario in [r.id for r in engine.rank("numerical linear algebra",
                                               limit=5).results]


def test_ppr_traverses_new_relations(store, mario):
    engine = NexusRank(store)
    g = engine.graph
    scores = local_ppr(g.P, {g.index["school:my:epfl"]: 1.0})
    assert scores[g.index[mario]] > 0
    assert np.isfinite(scores).all()
    path = g.explain_path({"field:my:numerical-methods": 1.0}, mario)
    assert path and path[-1].dst == mario


def test_demo_and_my_network_indices_are_separate(store, mario):
    my_engine = NexusRank(store)
    assert mario in [r.id for r in my_engine.rank("EPFL numerical", limit=5).results]
    assert my_engine.rank("quantum mechanics Manhattan Project", limit=5).seeds == []
    assert all(s["id"].split(":")[1] == "my" for s in my_engine.rank("EPFL", limit=5).seeds
               if s["type"] != "person")

    enrichment.set_pref(store, "active_dataset", "demo")
    demo_engine = NexusRank(store)
    assert mario not in demo_engine.graph.index
    assert demo_engine.rank("EPFL numerical", limit=5).seeds == []
    assert demo_engine.rank("quantum mechanics Manhattan Project", limit=5).results


def test_delete_enrichment_removes_relations_but_keeps_person(store, mario):
    enrichment.delete_enrichment(store, mario)
    assert store.conn.execute(
        "SELECT COUNT(*) FROM edges WHERE src=?", (mario,)).fetchone()[0] == 0
    assert store.conn.execute(
        "SELECT COUNT(*) FROM enrichment_item WHERE person_id=?",
        (mario,)).fetchone()[0] == 0
    prof = enrichment.get_profile(store, mario)
    assert prof is not None and prof["enriched"] is False
    assert mario not in dict(NexusRank(store).lex.search("EPFL"))


def test_imported_people_survive_clearing_enrichment(store):
    imported = store.conn.execute(
        "SELECT id FROM nodes WHERE type='person' LIMIT 1").fetchone()[0]
    degree_before = store.conn.execute(
        "SELECT COUNT(*) FROM edges WHERE src=? OR dst=?",
        (imported, imported)).fetchone()[0]
    enrichment.save_profile(store, imported, {"sections": {
        "skills": [{"name": "Numerical Linear Algebra"}]}})
    enrichment.delete_enrichment(store, imported)
    assert store.conn.execute(
        "SELECT 1 FROM nodes WHERE id=?", (imported,)).fetchone() is not None
    after = store.conn.execute(
        "SELECT COUNT(*) FROM edges WHERE src=? OR dst=?",
        (imported, imported)).fetchone()[0]
    assert after == degree_before


def test_manual_person_can_be_deleted(store, mario):
    assert enrichment.delete_person(store, mario) is True
    assert store.conn.execute(
        "SELECT 1 FROM nodes WHERE id=?", (mario,)).fetchone() is None


def test_imported_contact_cannot_be_deleted_with_person_delete(store):
    csv = ("First Name,Last Name,URL,Company,Position,Connected On\n"
           "Ada,Lovelace,https://www.linkedin.com/in/ada,Analytical Engines,Researcher,2024-01-02\n")
    pid = next(iter(enrichment.import_connections_csv(store, csv) and [
        r[0] for r in store.conn.execute("SELECT person_id FROM person_profile WHERE source_type='linkedin_csv'")
    ]))
    assert enrichment.delete_person(store, pid) is False
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (pid,)).fetchone() is not None


def test_import_csv_persists_and_upserts_after_restart(tmp_path):
    db = tmp_path / "nexus.db"
    csv = ("First Name,Last Name,URL,Company,Position,Connected On\n"
           "Ada,Lovelace,https://www.linkedin.com/in/ada,Analytical Engines,Researcher,2024-01-02\n")
    s1 = SQLiteStore(str(db))
    out = enrichment.import_connections_csv(s1, csv)
    pid = s1.conn.execute("SELECT person_id FROM person_profile").fetchone()[0]
    enrichment.save_profile(s1, pid, {**enrichment.get_profile(s1, pid),
                                      "sections": {"skills": [{"name": "Graph Search"}]}})
    enrichment.add_person(s1, {"name": "Manual Person", "sections": {"skills": [{"name": "BM25"}]}})
    assert out["people"] == 1
    enrichment.import_connections_csv(s1, csv)
    assert s1.conn.execute("SELECT COUNT(*) FROM person_profile WHERE source_type='linkedin_csv'").fetchone()[0] == 1

    s2 = SQLiteStore(str(db))
    enrichment.ensure_tables(s2)
    assert enrichment.get_pref(s2, "active_dataset") == "my"
    assert enrichment.my_network_count(s2) == 2
    assert s2.conn.execute("SELECT COUNT(*) FROM person_profile WHERE source_type='linkedin_csv'").fetchone()[0] == 1
    assert enrichment.get_profile(s2, pid)["sections"]["skills"][0]["name"] == "Graph Search"
    ranked = [r.id for r in NexusRank(s2).rank("graph search", limit=5).results]
    assert pid in ranked


def test_import_linkedin_csv_with_export_preamble(store):
    content = ("Notes:\nExported from LinkedIn\n\n"
               "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
               "Ada,Lovelace,https://www.linkedin.com/in/ada,,Analytical Engines,Researcher,2024-01-02\n")
    out = enrichment.import_connections_csv(store, content)
    assert out["imported"] == 1
    assert store.conn.execute(
        "SELECT COUNT(*) FROM person_profile WHERE source_type='linkedin_csv'"
    ).fetchone()[0] == 1


def test_import_linkedin_csv_semicolon_and_builds_edges(store):
    content = ("LinkedIn export\n\n"
               "First Name;Last Name;URL;Company;Position;Connected On\n"
               "Ada;Lovelace;https://www.linkedin.com/in/ada;ACME;Researcher;2024\n"
               "Grace;Hopper;https://www.linkedin.com/in/grace;ACME;Engineer;2024\n")
    out = enrichment.import_connections_csv(store, content)
    assert out["imported"] == 2
    imported = [r[0] for r in store.conn.execute(
        "SELECT person_id FROM person_profile WHERE source_type='linkedin_csv'")]
    assert store.conn.execute(
        "SELECT COUNT(*) FROM edges WHERE type='KNOWS' AND src IN (?,?)",
        tuple(imported),
    ).fetchone()[0] > 0


def test_import_linkedin_export_enriches_my_profile_and_network(store):
    files = [
        {"name": "Connections.csv", "content":
            "First Name,Last Name,URL,Company,Position,Connected On\n"
            "Ada,Lovelace,https://www.linkedin.com/in/ada,ACME,Researcher,2024\n"
            "Grace,Hopper,https://www.linkedin.com/in/grace,ACME,Engineer,2024\n"},
        {"name": "Profile.csv", "content":
            "First Name,Last Name,Headline,Summary,Geo Location\n"
            "Francesco,Roscio Ricon,Quant Student,Local profile,Milan\n"},
        {"name": "Positions.csv", "content":
            "Company Name,Title,Description,Location,Started On,Finished On\n"
            "Universita Pavia,Robotics Researcher,,,Jan 2024,Jun 2024\n"},
        {"name": "Education.csv", "content":
            "School Name,Start Date,End Date,Notes,Degree Name,Activities\n"
            "Politecnico di Milano,2025,2028,Mathematical Engineering,BSc,\n"},
        {"name": "Skills.csv", "content": "Name\nJulia\nRobotica\n"},
        {"name": "Certifications.csv", "content":
            "Name,Url,Authority,Started On,Finished On,License Number\n"
            "Python Certificate,,Harvard University,2026,,abc\n"},
        {"name": "Company Follows.csv", "content":
            "Organization,Followed On\nGoogle DeepMind,2026\n"},
        {"name": "Member_Follows_1.csv", "content":
            "Date,Status,FullName\n2026,Active,Eric Li\n"},
        {"name": "Saved_Items_1.csv", "content":
            "savedItem,CreatedTime\nhttps://www.linkedin.com/feed/update/1,2026\n"},
    ]
    out = enrichment.import_linkedin_export(store, files)
    assert out["imported"] == 2 and out["profile"] == "person:me"
    enrichment.set_pref(store, "active_dataset", "my")
    engine = NexusRank(store)
    g = engine.graph
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id='person:me'").fetchone()
    assert "person:me" not in g.index
    assert "company:my:acme" in g.index
    for nid in ("skill:my:julia", "skill:my:robotica",
                "school:my:politecnico-di-milano", "company:my:universita-pavia",
                "activity:my:google-deepmind", "project:my:python-certificate"):
        assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (nid,)).fetchone()
        assert nid not in g.index
    assert store.conn.execute(
        "SELECT COUNT(*) FROM edges WHERE src='person:me' AND type='KNOWS'"
    ).fetchone()[0] == 2
    ranked = engine.rank("Robotica Julia", limit=5)
    assert ranked.results == []
    assert "person:me" not in [s["id"] for s in ranked.seeds]
    sub = engine.subgraph("Robotica Julia", people=5)
    assert "person:me" not in {n["id"] for n in sub["nodes"]}
    assert all("person:me" not in (e["source"], e["target"]) for e in sub["edges"])


def test_legacy_user_nodes_are_moved_back_to_my_dataset(store):
    content = ("First Name,Last Name,URL,Company,Position,Connected On\n"
               "Ada,Lovelace,https://www.linkedin.com/in/ada,ACME,Researcher,2024\n")
    enrichment.import_connections_csv(store, content)
    imported = store.conn.execute(
        "SELECT person_id FROM person_profile WHERE source_type='linkedin_csv'"
    ).fetchone()[0]
    with store.conn:
        store.conn.execute("UPDATE nodes SET dataset='demo' WHERE dataset='my'")
        store.conn.execute("UPDATE edges SET dataset='demo' WHERE dataset='my'")
    enrichment.ensure_tables(store)
    enrichment.set_pref(store, "active_dataset", "my")
    assert imported in NexusRank(store).graph.index
    assert NexusRank(store).rank("ACME", limit=5).results


def test_clear_my_network_removes_user_network(store, mario):
    pid = store.conn.execute(
        "SELECT id FROM nodes WHERE type='person' LIMIT 1").fetchone()[0]
    csv = ("First Name,Last Name,URL,Company,Position,Connected On\n"
           "Ada,Lovelace,https://www.linkedin.com/in/ada,Analytical Engines,Researcher,2024-01-02\n")
    enrichment.import_connections_csv(store, csv)
    imported = store.conn.execute(
        "SELECT person_id FROM person_profile WHERE source_type='linkedin_csv'").fetchone()[0]
    assert enrichment.clear_my_network(store) == 2
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (imported,)).fetchone() is None
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (mario,)).fetchone() is None
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (pid,)).fetchone() is not None


def test_clear_my_network_removes_legacy_linkedin_ids_and_manual_people(store):
    csv = ("First Name,Last Name,URL,Company,Position,Connected On\n"
           "Ada,Lovelace,https://www.linkedin.com/in/ada,Analytical Engines,Researcher,2024-01-02\n")
    enrichment.import_connections_csv(store, csv)
    imported = store.conn.execute(
        "SELECT person_id FROM person_profile WHERE source_type='linkedin_csv'").fetchone()[0]
    with store.conn:
        store.conn.execute("UPDATE person_profile SET source_type='manual' WHERE person_id=?", (imported,))
    manual = enrichment.add_person(store, {"name": "Manual Person"})["id"]
    assert enrichment.clear_my_network(store) == 2
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (imported,)).fetchone() is None
    assert store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (manual,)).fetchone() is None
