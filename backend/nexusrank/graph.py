"""In-memory heterogeneous graph: CSR transition matrix + adjacency for paths."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp

from .schema import EDGE_TYPES
from .store import Edge, GraphStore, Node


@dataclass(slots=True)
class Hop:
    src: str
    dst: str
    type: str
    weight: float


class HeteroGraph:
    """Typed multi-relational graph, materialised as one sparse operator.

    Edge weight = stored weight x relation prior from `schema.EDGE_TYPES`; every
    relation is expanded symmetrically so influence can flow person -> skill ->
    person. The matrix is column-stochastic, so PPR is a plain mat-vec.
    """

    def __init__(self, nodes: list[Node], edges: list[Edge]) -> None:
        self.nodes = nodes
        self.index = {n.id: i for i, n in enumerate(nodes)}
        self.by_id = {n.id: n for n in nodes}
        n = len(nodes)

        rows, cols, vals = [], [], []
        self.adj: dict[str, list[Hop]] = {nd.id: [] for nd in nodes}
        for e in edges:
            if e.src not in self.index or e.dst not in self.index:
                continue
            prior = EDGE_TYPES.get(e.type, ("", "", 0.5, True))[2]
            w = e.weight * prior
            i, j = self.index[e.src], self.index[e.dst]
            rows += [j, i]
            cols += [i, j]
            vals += [w, w]
            self.adj[e.src].append(Hop(e.src, e.dst, e.type, w))
            self.adj[e.dst].append(Hop(e.dst, e.src, e.type, w))

        A = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
        self.A = A
        self.out_strength = np.asarray(A.sum(axis=0)).ravel()
        inv = np.divide(1.0, self.out_strength, out=np.zeros(n),
                        where=self.out_strength > 0)
        # column-stochastic transition operator P[:, i] = A[:, i] / sum
        self.P = (A @ sp.diags(inv)).tocsr()

    def __len__(self) -> int:
        return len(self.nodes)

    def ids_of_type(self, t: str) -> list[str]:
        return [n.id for n in self.nodes if n.type == t]

    def explain_path(self, seeds: dict[str, float], target: str,
                     max_hops: int = 4) -> list[Hop]:
        """Cheapest evidence chain from the best-matching seed to `target`.

        Cost of a hop is -log(weight): multiplying trust becomes adding cost, so
        Dijkstra returns the single most probable explanation path.
        """
        # A target that is itself a seed still gets explained, from the *other*
        # seeds — "you matched the query" is not evidence a user can act on.
        start_cost = {s: -math.log(max(w, 1e-9)) for s, w in seeds.items()
                      if s in self.index and s != target}
        if not start_cost:
            return []
        tick = 0  # tiebreaker: Hop tuples are not orderable
        pq = [(c, i, s, ()) for i, (s, c) in enumerate(start_cost.items())]
        heapq.heapify(pq)
        seen: set[str] = set()
        while pq:
            cost, _, node, path = heapq.heappop(pq)
            if node in seen:
                continue
            seen.add(node)
            if node == target:
                return list(path)
            if len(path) >= max_hops:
                continue
            for h in self.adj.get(node, ()):
                if h.dst not in seen:
                    tick += 1
                    heapq.heappush(pq, (cost - math.log(max(h.weight, 1e-9)),
                                        tick, h.dst, path + (h,)))
        return []


def load_graph(store: GraphStore) -> HeteroGraph:
    return HeteroGraph(store.nodes(), store.edges())
