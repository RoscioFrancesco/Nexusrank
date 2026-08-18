"""NexusRank engine: lexical retrieval + query-conditioned PPR + score fusion."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .graph import HeteroGraph
from .lexical import BM25Index
from .schema import EDGE_LABELS
from .store import GraphStore


@dataclass(slots=True)
class Result:
    id: str
    name: str
    type: str
    meta: str
    score: float
    graph_score: float
    lexical_score: float
    path: list[dict] = field(default_factory=list)
    why: str = ""


@dataclass(slots=True)
class SearchResponse:
    query: str
    seeds: list[dict]
    results: list[Result]
    solver: str

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "seeds": self.seeds,
            "solver": self.solver,
            "results": [asdict(r) for r in self.results],
        }


# Concept nodes are the useful random-walk sources: a query names a topic, and
# the skill/company node for that topic sits at the centre of the people who own
# it. Posts match lexically but are short and noisy, so they are damped.
SEED_BOOST = {"skill": 2.6, "company": 2.2, "school": 1.8, "person": 1.0, "post": 0.7}


def _unit(x: np.ndarray) -> np.ndarray:
    hi = float(x.max()) if x.size else 0.0
    return x / hi if hi > 0 else x


class NexusRank:
    """Holds the derived indices. Rebuild on write; read paths are pure."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.graph = HeteroGraph(store.nodes(), store.edges())
        self.lex = BM25Index(self.graph.nodes)

    # ---- query conditioning -------------------------------------------------

    def seeds_for(self, query: str, viewer: str | None = None,
                  top_seeds: int = 12, viewer_share: float = 0.5) -> dict[str, float]:
        """Turn a text query into a weighted seed set over *any* node type.

        Skills/companies/schools make far better random-walk sources than people,
        so non-person matches are up-weighted: the walk then finds people who are
        central to the query's concepts rather than people whose profile happens
        to repeat the query terms.
        """
        hits = self.lex.search(query, limit=top_seeds * 4)
        seeds: dict[str, float] = {}
        for nid, score in hits:
            node = self.graph.by_id[nid]
            seeds[nid] = score * SEED_BOOST.get(node.type, 1.0)
        seeds = dict(sorted(seeds.items(), key=lambda kv: -kv[1])[:top_seeds])
        if viewer and viewer in self.graph.index:
            # `viewer_share` of the restart mass is spent on "me", so the walk
            # ranks the query *relative to my corner of the network*.
            rest = sum(w for k, w in seeds.items() if k != viewer) or 1.0
            seeds[viewer] = rest * viewer_share / max(1 - viewer_share, 1e-6)
        return seeds

    def rank(self, query: str, viewer: str | None = None, limit: int = 10,
             node_type: str = "person", graph_weight: float = 0.75,
             alpha: float = 0.15, solver: str = "local") -> SearchResponse:
        from .ppr import local_ppr, power_ppr, seed_vector

        g = self.graph
        seeds = self.seeds_for(query, viewer)
        idx_seeds = {g.index[k]: v for k, v in seeds.items() if k in g.index}

        if solver == "local":
            ppr = local_ppr(g.P, idx_seeds, alpha=alpha)
        else:
            ppr = power_ppr(g.P, seed_vector(len(g), idx_seeds), alpha=alpha)

        lex = np.zeros(len(g))
        for nid, s in self.lex.search(query, limit=400):
            lex[g.index[nid]] = s

        candidates = np.array([i for i, n in enumerate(g.nodes)
                               if n.type == node_type], dtype=int)
        gs, ls = _unit(ppr[candidates]), _unit(lex[candidates])
        fused = graph_weight * gs + (1 - graph_weight) * ls
        order = np.argsort(-fused)[: limit * 2]

        results: list[Result] = []
        for pos in order:
            i = int(candidates[pos])
            node = g.nodes[i]
            if node.id == viewer:       # never recommend the viewer to themself
                continue
            path = g.explain_path(seeds, node.id)
            results.append(Result(
                id=node.id, name=node.name, type=node.type, meta=node.meta,
                score=round(float(fused[pos]), 6),
                graph_score=round(float(gs[pos]), 6),
                lexical_score=round(float(ls[pos]), 6),
                path=[{"src": h.src, "dst": h.dst, "type": h.type,
                       "label": EDGE_LABELS.get(h.type, h.type),
                       "weight": round(h.weight, 4)} for h in path],
                why=self._why(node.id, path, seeds),
            ))
            if len(results) == limit:
                break

        seed_out = [{"id": k, "name": self.graph.by_id[k].name,
                     "type": self.graph.by_id[k].type, "weight": round(v, 4)}
                    for k, v in seeds.items()]
        return SearchResponse(query=query, seeds=seed_out, results=results,
                              solver=solver)

    def _why(self, target: str, path, seeds: dict[str, float]) -> str:
        if not path:
            return "Directly matches the query." if target in seeds else "Query seed."
        parts = [self.graph.by_id[path[0].src].name]
        for h in path:
            parts.append(f"—{EDGE_LABELS.get(h.type, h.type)}→ "
                         f"{self.graph.by_id[h.dst].name}")
        return " ".join(parts)

    # ---- visualisation -----------------------------------------------------

    def subgraph(self, query: str, viewer: str | None = None,
                 people: int = 24) -> dict:
        """Query-conditioned subgraph: top-ranked people + the seeds and the
        concept nodes that connect them. Small enough for Sigma to lay out live."""
        g = self.graph
        resp = self.rank(query, viewer=viewer, limit=people)
        keep = {r.id for r in resp.results} | {s["id"] for s in resp.seeds}
        for r in resp.results:
            for hop in r.path:
                keep.add(hop["src"])
                keep.add(hop["dst"])
        if viewer:
            keep.add(viewer)

        score = {r.id: r.score for r in resp.results}
        seed_ids = {s["id"] for s in resp.seeds}
        nodes = [{"id": nid, "label": g.by_id[nid].name, "type": g.by_id[nid].type,
                  "meta": g.by_id[nid].meta, "score": score.get(nid, 0.0),
                  "seed": nid in seed_ids} for nid in keep]
        edges, seen = [], set()
        for nid in keep:
            for h in g.adj.get(nid, ()):
                if h.dst in keep:
                    k = tuple(sorted((h.src, h.dst))) + (h.type,)
                    if k not in seen:
                        seen.add(k)
                        edges.append({"source": h.src, "target": h.dst,
                                      "type": h.type, "weight": round(h.weight, 4),
                                      "label": EDGE_LABELS.get(h.type, h.type)})
        return {"query": query, "nodes": nodes, "edges": edges,
                "results": [asdict(r) for r in resp.results],
                "seeds": resp.seeds}
