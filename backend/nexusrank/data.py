"""Deterministic synthetic professional network.

Communities are generated explicitly (dense intra-cluster KNOWS, sparse bridges)
so that query-conditioned PPR has real structure to exploit.
"""
from __future__ import annotations

import random

from .store import Edge, GraphStore, Node

CLUSTERS = {
    "ml": {
        "label": "Machine Learning",
        "skills": ["PyTorch", "LLMs", "Recommender Systems", "Graph Neural Networks",
                   "Information Retrieval", "MLOps"],
        "companies": ["Vectorly", "Northwind AI", "Latent Labs", "Helix Research"],
        "titles": ["ML Engineer", "Research Scientist", "Applied Scientist",
                   "Search Relevance Engineer", "Head of AI"],
    },
    "infra": {
        "label": "Platform & Infra",
        "skills": ["Kubernetes", "Rust", "Distributed Systems", "PostgreSQL",
                   "Observability", "Go"],
        "companies": ["Sundial Systems", "Bitforge", "Corvus Cloud", "Meridian Data"],
        "titles": ["Staff Engineer", "SRE", "Backend Engineer", "Platform Lead",
                   "Principal Architect"],
    },
    "product": {
        "label": "Product & Design",
        "skills": ["Product Strategy", "Design Systems", "User Research",
                   "Figma", "Growth Analytics", "Accessibility"],
        "companies": ["Kestrel", "Bloomline", "Tandem Studio", "Orchard Labs"],
        "titles": ["Product Manager", "Design Lead", "UX Researcher",
                   "Group PM", "Director of Product"],
    },
    "fin": {
        "label": "Fintech & Quant",
        "skills": ["Risk Modeling", "Time Series", "Payments", "C++",
                   "Market Microstructure", "Compliance"],
        "companies": ["Ledgerline", "Quantis Capital", "Aurum Pay", "Solstice Bank"],
        "titles": ["Quant Researcher", "Risk Analyst", "Payments Engineer",
                   "Trading Systems Engineer", "VP Engineering"],
    },
    "bio": {
        "label": "Bio & Health",
        "skills": ["Genomics", "Clinical Trials", "Bioinformatics", "R",
                   "Medical Imaging", "Regulatory Affairs"],
        "companies": ["Cytoform", "Halcyon Bio", "Verdant Health", "Nucleus Dx"],
        "titles": ["Computational Biologist", "Data Scientist", "Clinical Lead",
                   "Imaging Scientist", "Chief Scientist"],
    },
}

SCHOOLS = ["Bellhaven University", "Kingsmere Institute of Technology", "Ravenwood College",
           "Aldermere Polytechnic", "Saint Ivo University", "Tessellate School of Design"]

FIRST = ["Ada", "Rafael", "Mei", "Jonas", "Priya", "Tomas", "Nadia", "Ivan", "Sofia", "Kwame",
         "Lena", "Hugo", "Amara", "Dmitri", "Yara", "Oscar", "Ines", "Kenji", "Zoe", "Malik",
         "Freya", "Bruno", "Anika", "Luca", "Noor", "Elias", "Chiara", "Ravi", "Greta", "Samir"]
LAST = ["Okafor", "Lindqvist", "Moreau", "Tanaka", "Ferreira", "Vasquez", "Novak", "Haddad",
        "Bergström", "Ionescu", "Kowalski", "Rossi", "Delgado", "Nakamura", "Petrov",
        "Abadi", "Sørensen", "Marchetti", "Dubois", "Ashworth"]
CITIES = ["Milan", "Berlin", "London", "Lisbon", "Amsterdam", "Zurich", "Austin",
          "Toronto", "Singapore", "New York"]

POST_TEMPLATES = [
    "Why {s} is quietly reshaping how we build {s2} systems",
    "Notes from six months of {s} in production",
    "Hiring: we need someone who lives and breathes {s}",
    "A short field guide to {s} for {s2} teams",
    "What I got wrong about {s}",
]


def generate(store: GraphStore, n_people: int = 180, seed: int = 7) -> None:
    rng = random.Random(seed)
    nodes: list[Node] = []
    edges: list[Edge] = []

    for name in SCHOOLS:
        nodes.append(Node(f"school:{_slug(name)}", "school", name, "university school"))

    skill_of: dict[str, str] = {}
    for key, c in CLUSTERS.items():
        for s in c["skills"]:
            sid = f"skill:{_slug(s)}"
            skill_of[s] = sid
            nodes.append(Node(sid, "skill", s, f"{s} {c['label']}", c["label"]))
        for comp in c["companies"]:
            cid = f"company:{_slug(comp)}"
            nodes.append(Node(cid, "company", comp, f"{comp} {c['label']} company",
                              c["label"]))
            for s in rng.sample(c["skills"], 3):
                edges.append(Edge(cid, skill_of[s], "REQUIRES"))

    members: dict[str, list[str]] = {k: [] for k in CLUSTERS}
    keys = list(CLUSTERS)
    for i in range(n_people):
        key = keys[i % len(keys)]
        c = CLUSTERS[key]
        pid = f"person:{i:04d}"
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        title = rng.choice(c["titles"])
        company = rng.choice(c["companies"])
        city = rng.choice(CITIES)
        skills = rng.sample(c["skills"], 3)
        # 30% of people bridge into a second domain -> interesting cross-cluster paths
        if rng.random() < 0.30:
            other = CLUSTERS[rng.choice([k for k in keys if k != key])]
            skills.append(rng.choice(other["skills"]))
        headline = f"{title} at {company}"
        nodes.append(Node(
            pid, "person", name,
            f"{headline} {city} {' '.join(skills)} {c['label']}",
            f"{headline} · {city}",
        ))
        members[key].append(pid)
        edges.append(Edge(pid, f"company:{_slug(company)}", "WORKED_AT"))
        edges.append(Edge(pid, f"school:{_slug(rng.choice(SCHOOLS))}", "STUDIED_AT"))
        for s in skills:
            edges.append(Edge(pid, skill_of[s], "HAS_SKILL", 0.9 if s in c["skills"] else 0.5))

        if rng.random() < 0.55:
            s, s2 = rng.sample(skills, 2) if len(skills) > 1 else (skills[0], skills[0])
            post_id = f"post:{i:04d}"
            body = rng.choice(POST_TEMPLATES).format(s=s, s2=s2)
            nodes.append(Node(post_id, "post", body, f"{body} {s} {s2}", f"post by {name}"))
            edges.append(Edge(pid, post_id, "AUTHORED"))
            edges.append(Edge(post_id, skill_of[s], "MENTIONS"))

    # small-world KNOWS: ring lattice + random intra-cluster chords + rare bridges
    for key, group in members.items():
        n = len(group)
        for i, pid in enumerate(group):
            for off in (1, 2):
                edges.append(Edge(pid, group[(i + off) % n], "KNOWS", 1.0))
            for _ in range(rng.randint(1, 4)):
                other = rng.choice(group)
                if other != pid:
                    edges.append(Edge(pid, other, "KNOWS", 0.9))
    all_people = [p for g in members.values() for p in g]
    for _ in range(int(0.35 * len(all_people))):
        a, b = rng.sample(all_people, 2)
        edges.append(Edge(a, b, "KNOWS", 0.6))

    store.write(nodes, _dedupe(edges))


def _dedupe(edges: list[Edge]) -> list[Edge]:
    best: dict[tuple[str, str, str], Edge] = {}
    for e in edges:
        k = (e.src, e.dst, e.type)
        if k not in best or e.weight > best[k].weight:
            best[k] = e
    return list(best.values())


def _slug(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in s).strip("-")
