"""Deterministic demo network: Manhattan Project physicists and mathematicians."""
from __future__ import annotations

from .store import Edge, GraphStore, Node

MANHATTAN_SCIENTISTS = [
    {
        "key": "oppenheimer", "id": "person:hist:oppenheimer",
        "name": "J. Robert Oppenheimer", "title": "Scientific Director",
        "org": "Los Alamos Laboratory", "school": "University of Gottingen",
        "location": "Los Alamos",
        "skills": ["Quantum Mechanics", "Quantum Field Theory", "Nuclear Physics"],
        "projects": ["Manhattan Project", "Los Alamos Theoretical Program"],
        "activity": "Theoretical Physics",
        "notes": "Led the scientific work at Los Alamos during the Manhattan Project.",
    },
    {
        "key": "fermi", "id": "person:hist:fermi",
        "name": "Enrico Fermi", "title": "Nuclear Physicist",
        "org": "University of Chicago Metallurgical Laboratory",
        "school": "Scuola Normale Superiore", "location": "Chicago",
        "skills": ["Reactor Physics", "Statistical Mechanics", "Nuclear Chain Reaction"],
        "projects": ["Chicago Pile-1", "Manhattan Project"],
        "activity": "Experimental Physics",
        "notes": "Led the first controlled self-sustaining nuclear chain reaction.",
    },
    {
        "key": "bohr", "id": "person:hist:bohr",
        "name": "Niels Bohr", "title": "Quantum Theorist",
        "org": "Los Alamos Laboratory", "school": "University of Copenhagen",
        "location": "Los Alamos",
        "skills": ["Quantum Mechanics", "Atomic Theory", "Nuclear Physics"],
        "projects": ["Manhattan Project", "Copenhagen Interpretation"],
        "activity": "Theoretical Physics",
        "notes": "Advised Manhattan Project scientists under the name Nicholas Baker.",
    },
    {
        "key": "feynman", "id": "person:hist:feynman",
        "name": "Richard Feynman", "title": "Theoretical Physicist",
        "org": "Los Alamos Laboratory", "school": "Princeton University",
        "location": "Los Alamos",
        "skills": ["Quantum Electrodynamics", "Path Integrals", "Nuclear Physics"],
        "projects": ["Manhattan Project", "Los Alamos Theoretical Program"],
        "activity": "Theoretical Physics",
        "notes": "Worked in the theoretical division at Los Alamos.",
    },
    {
        "key": "bethe", "id": "person:hist:bethe",
        "name": "Hans Bethe", "title": "Head of Theoretical Division",
        "org": "Los Alamos Laboratory", "school": "University of Munich",
        "location": "Los Alamos",
        "skills": ["Nuclear Physics", "Stellar Nucleosynthesis", "Quantum Mechanics"],
        "projects": ["Manhattan Project", "Los Alamos Theoretical Program"],
        "activity": "Theoretical Physics",
        "notes": "Led the theoretical division at Los Alamos.",
    },
    {
        "key": "teller", "id": "person:hist:teller",
        "name": "Edward Teller", "title": "Theoretical Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Leipzig",
        "location": "Los Alamos",
        "skills": ["Nuclear Physics", "Molecular Physics", "Quantum Mechanics"],
        "projects": ["Manhattan Project", "Thermonuclear Research"],
        "activity": "Theoretical Physics",
        "notes": "Worked on theoretical physics problems at Los Alamos.",
    },
    {
        "key": "szilard", "id": "person:hist:szilard",
        "name": "Leo Szilard", "title": "Physicist and Inventor",
        "org": "University of Chicago Metallurgical Laboratory",
        "school": "Technical University of Berlin", "location": "Chicago",
        "skills": ["Nuclear Chain Reaction", "Nuclear Physics", "Scientific Policy"],
        "projects": ["Manhattan Project", "Einstein-Szilard Letter"],
        "activity": "Nuclear Research",
        "notes": "Helped initiate early atomic research and worked at the Metallurgical Laboratory.",
    },
    {
        "key": "lawrence", "id": "person:hist:lawrence",
        "name": "Ernest Lawrence", "title": "Experimental Physicist",
        "org": "Berkeley Radiation Laboratory", "school": "Yale University",
        "location": "Berkeley",
        "skills": ["Cyclotron Design", "Isotope Separation", "Nuclear Physics"],
        "projects": ["Manhattan Project", "Electromagnetic Isotope Separation"],
        "activity": "Experimental Physics",
        "notes": "Built cyclotron programs and contributed to isotope separation.",
    },
    {
        "key": "vonneumann", "id": "person:hist:vonneumann",
        "name": "John von Neumann", "title": "Mathematician",
        "org": "Los Alamos Laboratory", "school": "University of Budapest",
        "location": "Los Alamos",
        "skills": ["Mathematical Physics", "Shock Waves", "Implosion Calculations"],
        "projects": ["Manhattan Project", "Implosion Lens Calculations"],
        "activity": "Applied Mathematics",
        "notes": "Applied mathematical analysis to implosion and shock wave problems.",
    },
    {
        "key": "ulam", "id": "person:hist:ulam",
        "name": "Stanislaw Ulam", "title": "Mathematician",
        "org": "Los Alamos Laboratory", "school": "Lwow Polytechnic",
        "location": "Los Alamos",
        "skills": ["Applied Mathematics", "Monte Carlo Methods", "Nuclear Calculations"],
        "projects": ["Manhattan Project", "Los Alamos Computation"],
        "activity": "Applied Mathematics",
        "notes": "Worked as a mathematician at Los Alamos.",
    },
    {
        "key": "segre", "id": "person:hist:segre",
        "name": "Emilio Segre", "title": "Experimental Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Rome",
        "location": "Los Alamos",
        "skills": ["Nuclear Physics", "Radioactivity", "Plutonium Physics"],
        "projects": ["Manhattan Project", "Plutonium Measurements"],
        "activity": "Experimental Physics",
        "notes": "Measured nuclear properties important to Los Alamos work.",
    },
    {
        "key": "alvarez", "id": "person:hist:alvarez",
        "name": "Luis Alvarez", "title": "Experimental Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Chicago",
        "location": "Los Alamos",
        "skills": ["Experimental Physics", "Detonators", "Nuclear Measurements"],
        "projects": ["Manhattan Project", "Implosion Diagnostics"],
        "activity": "Experimental Physics",
        "notes": "Worked on detonators and diagnostics for the implosion program.",
    },
    {
        "key": "wu", "id": "person:hist:wu",
        "name": "Chien-Shiung Wu", "title": "Experimental Physicist",
        "org": "Columbia University", "school": "University of California Berkeley",
        "location": "New York",
        "skills": ["Experimental Physics", "Beta Decay", "Uranium Enrichment"],
        "projects": ["Manhattan Project", "Gaseous Diffusion"],
        "activity": "Experimental Physics",
        "notes": "Worked on radiation detection and uranium enrichment problems.",
    },
    {
        "key": "goeppertmayer", "id": "person:hist:goeppert-mayer",
        "name": "Maria Goeppert Mayer", "title": "Theoretical Physicist",
        "org": "Columbia University", "school": "University of Gottingen",
        "location": "New York",
        "skills": ["Nuclear Physics", "Statistical Mechanics", "Isotope Separation"],
        "projects": ["Manhattan Project", "Uranium Isotope Separation"],
        "activity": "Theoretical Physics",
        "notes": "Worked on isotope separation research during the Manhattan Project.",
    },
    {
        "key": "woods", "id": "person:hist:woods",
        "name": "Leona Woods", "title": "Experimental Physicist",
        "org": "University of Chicago Metallurgical Laboratory",
        "school": "University of Chicago", "location": "Chicago",
        "skills": ["Reactor Physics", "Neutron Detection", "Nuclear Chain Reaction"],
        "projects": ["Chicago Pile-1", "Manhattan Project"],
        "activity": "Experimental Physics",
        "notes": "Worked on Chicago Pile-1 instrumentation and reactor physics.",
    },
    {
        "key": "serber", "id": "person:hist:serber",
        "name": "Robert Serber", "title": "Theoretical Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Wisconsin",
        "location": "Los Alamos",
        "skills": ["Theoretical Physics", "Nuclear Physics", "Bomb Design"],
        "projects": ["Manhattan Project", "Los Alamos Primer"],
        "activity": "Theoretical Physics",
        "notes": "Prepared the Los Alamos Primer for incoming scientists.",
    },
    {
        "key": "weisskopf", "id": "person:hist:weisskopf",
        "name": "Victor Weisskopf", "title": "Theoretical Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Gottingen",
        "location": "Los Alamos",
        "skills": ["Quantum Field Theory", "Nuclear Physics", "Theoretical Physics"],
        "projects": ["Manhattan Project", "Los Alamos Theoretical Program"],
        "activity": "Theoretical Physics",
        "notes": "Worked in the Los Alamos theoretical division.",
    },
    {
        "key": "frisch", "id": "person:hist:frisch",
        "name": "Otto Frisch", "title": "Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Vienna",
        "location": "Los Alamos",
        "skills": ["Nuclear Fission", "Experimental Physics", "Critical Mass"],
        "projects": ["Manhattan Project", "British Mission"],
        "activity": "Experimental Physics",
        "notes": "Joined the British Mission and worked at Los Alamos.",
    },
    {
        "key": "peierls", "id": "person:hist:peierls",
        "name": "Rudolf Peierls", "title": "Theoretical Physicist",
        "org": "Los Alamos Laboratory", "school": "University of Leipzig",
        "location": "Los Alamos",
        "skills": ["Theoretical Physics", "Critical Mass", "Nuclear Fission"],
        "projects": ["Manhattan Project", "British Mission"],
        "activity": "Theoretical Physics",
        "notes": "Joined the British Mission and contributed theoretical calculations.",
    },
    {
        "key": "chadwick", "id": "person:hist:chadwick",
        "name": "James Chadwick", "title": "Physicist",
        "org": "British Mission", "school": "University of Manchester",
        "location": "Los Alamos",
        "skills": ["Neutron Physics", "Nuclear Physics", "Scientific Coordination"],
        "projects": ["Manhattan Project", "British Mission"],
        "activity": "Experimental Physics",
        "notes": "Led the British Mission scientific contribution to the Manhattan Project.",
    },
    {
        "key": "wheeler", "id": "person:hist:wheeler",
        "name": "John Archibald Wheeler", "title": "Theoretical Physicist",
        "org": "University of Chicago Metallurgical Laboratory",
        "school": "Johns Hopkins University", "location": "Chicago",
        "skills": ["Nuclear Physics", "Reactor Physics", "Quantum Theory"],
        "projects": ["Manhattan Project", "Nuclear Reactor Research"],
        "activity": "Theoretical Physics",
        "notes": "Worked on reactor and nuclear physics problems during the project.",
    },
    {
        "key": "neddermeyer", "id": "person:hist:neddermeyer",
        "name": "Seth Neddermeyer", "title": "Experimental Physicist",
        "org": "Los Alamos Laboratory", "school": "California Institute of Technology",
        "location": "Los Alamos",
        "skills": ["Implosion Design", "Cosmic Rays", "Experimental Physics"],
        "projects": ["Manhattan Project", "Implosion Program"],
        "activity": "Experimental Physics",
        "notes": "Proposed and developed early implosion concepts at Los Alamos.",
    },
]

MANHATTAN_KNOWS = [
    ("oppenheimer", "fermi"), ("oppenheimer", "bohr"), ("oppenheimer", "feynman"),
    ("oppenheimer", "bethe"), ("oppenheimer", "teller"), ("oppenheimer", "vonneumann"),
    ("oppenheimer", "ulam"), ("oppenheimer", "serber"), ("oppenheimer", "weisskopf"),
    ("oppenheimer", "segre"), ("oppenheimer", "alvarez"), ("oppenheimer", "neddermeyer"),
    ("fermi", "szilard"), ("fermi", "woods"), ("fermi", "wheeler"),
    ("fermi", "lawrence"), ("fermi", "bohr"), ("bethe", "feynman"),
    ("bethe", "teller"), ("bethe", "weisskopf"), ("szilard", "wheeler"),
    ("lawrence", "alvarez"), ("lawrence", "segre"), ("vonneumann", "ulam"),
    ("vonneumann", "neddermeyer"), ("wu", "goeppertmayer"),
    ("frisch", "peierls"), ("frisch", "chadwick"), ("peierls", "chadwick"),
    ("bohr", "chadwick"), ("serber", "feynman"),
]


def generate(store: GraphStore, n_people: int = 180, seed: int = 7) -> None:
    """Compatibility entrypoint; demo size/seed are intentionally ignored."""
    ensure_manhattan_demo(store, reset=True)


def ensure_manhattan_demo(store: GraphStore, reset: bool = False) -> None:
    """Keep demo data limited to Manhattan Project physicists/mathematicians."""
    conn = getattr(store, "conn", None)
    allowed = [p["id"] for p in MANHATTAN_SCIENTISTS]
    if conn is not None and not reset:
        placeholders = ",".join("?" for _ in allowed)
        bad = conn.execute(
            f"SELECT COUNT(*) FROM nodes WHERE dataset='demo' AND type='person' "
            f"AND id NOT IN ({placeholders})",
            allowed,
        ).fetchone()[0]
        have = conn.execute(
            f"SELECT COUNT(*) FROM nodes WHERE dataset='demo' AND type='person' "
            f"AND id IN ({placeholders})",
            allowed,
        ).fetchone()[0]
        reset = bool(bad) or have != len(allowed)

    if reset:
        _clear_demo(store)
    _write_manhattan_demo(store)


def ensure_historical_demo(store: GraphStore) -> None:
    ensure_manhattan_demo(store)


def _write_manhattan_demo(store: GraphStore) -> None:
    nodes: list[Node] = []
    edges: list[Edge] = []
    seen_nodes: set[str] = set()

    def node(nid: str, ntype: str, name: str, text: str = "", meta: str = "") -> None:
        if nid not in seen_nodes:
            seen_nodes.add(nid)
            nodes.append(Node(nid, ntype, name, text or name, meta))

    for p in MANHATTAN_SCIENTISTS:
        headline = f"{p['title']} at {p['org']}"
        text = " ".join([
            p["name"], headline, p["location"], p["school"], p["activity"],
            " ".join(p["skills"]), " ".join(p["projects"]), p["notes"],
        ])
        node(p["id"], "person", p["name"], text, f"{headline} · {p['location']}")

        org_id = f"company:{_slug(p['org'])}"
        school_id = f"school:{_slug(p['school'])}"
        activity_id = f"activity:{_slug(p['activity'])}"
        node(org_id, "company", p["org"], f"{p['org']} Manhattan Project institution",
             "Manhattan Project")
        node(school_id, "school", p["school"], f"{p['school']} university", "school")
        node(activity_id, "activity", p["activity"], p["activity"], "activity")
        edges += [
            Edge(p["id"], org_id, "WORKED_AT", 1.0),
            Edge(p["id"], school_id, "STUDIED_AT", 0.8),
            Edge(p["id"], activity_id, "MEMBER_OF", 0.7),
        ]

        for skill in p["skills"]:
            sid = f"skill:{_slug(skill)}"
            node(sid, "skill", skill, f"{skill} Manhattan Project physics", "science")
            edges.append(Edge(p["id"], sid, "HAS_SKILL", 0.95))
        for project in p["projects"]:
            pid = f"project:{_slug(project)}"
            node(pid, "project", project, f"{project} Manhattan Project", "project")
            edges.append(Edge(p["id"], pid, "WORKED_ON", 0.9))

    ids = {p["key"]: p["id"] for p in MANHATTAN_SCIENTISTS}
    for a, b in MANHATTAN_KNOWS:
        if a in ids and b in ids:
            edges.append(Edge(ids[a], ids[b], "KNOWS", 0.85))

    store.write(nodes, _dedupe(edges), dataset="demo")


def _clear_demo(store: GraphStore) -> None:
    conn = getattr(store, "conn", None)
    if conn is None:
        return
    with conn:
        conn.execute("DELETE FROM edges WHERE dataset='demo'")
        conn.execute("DELETE FROM nodes WHERE dataset='demo'")


def _dedupe(edges: list[Edge]) -> list[Edge]:
    best: dict[tuple[str, str, str], Edge] = {}
    for e in edges:
        k = (e.src, e.dst, e.type)
        if k not in best or e.weight > best[k].weight:
            best[k] = e
    return list(best.values())


def _slug(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in s).strip("-")
