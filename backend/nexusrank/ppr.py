"""Query-conditioned Personalized PageRank.

Two interchangeable solvers over the same sparse operator:
  * `power_ppr` - global solution by power iteration, O(nnz) per step.
  * `local_ppr` - Andersen-Chung-Lang push; touches only the neighbourhood around
                  the seeds, which is what keeps per-query ranking cheap when the
                  graph is far larger than the seed set.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp


def seed_vector(n: int, seeds: dict[int, float]) -> np.ndarray:
    """L1-normalised personalization vector; uniform if the query matched nothing."""
    v = np.zeros(n)
    for i, w in seeds.items():
        v[i] += max(w, 0.0)
    total = v.sum()
    if total <= 0:
        return np.full(n, 1.0 / n)
    return v / total


def power_ppr(P: sp.csr_matrix, s: np.ndarray, alpha: float = 0.15,
              tol: float = 1e-10, max_iter: int = 200) -> np.ndarray:
    """r = alpha*s + (1-alpha)*P r; mass lost at dangling nodes returns to seeds."""
    r = s.copy()
    for _ in range(max_iter):
        nxt = alpha * s + (1 - alpha) * (P @ r)
        leak = 1.0 - nxt.sum()
        if leak > 1e-15:
            nxt = nxt + leak * s
        delta = np.abs(nxt - r).sum()
        r = nxt
        if delta < tol:
            break
    return r


def local_ppr(P: sp.csr_matrix, seeds: dict[int, float], alpha: float = 0.15,
              eps: float = 1e-7, max_rounds: int = 300) -> np.ndarray:
    """Batched ACL push: each round retires every residual above `eps` at once.

    Only the columns of P belonging to active nodes are ever touched, so the cost
    scales with the explored neighbourhood rather than with |V| — while staying a
    vectorised sparse op instead of a Python-level push loop.
    """
    n = P.shape[0]
    Pc = P.tocsc()
    p = np.zeros(n)
    r = seed_vector(n, seeds)
    for _ in range(max_rounds):
        active = np.flatnonzero(r > eps)
        if active.size == 0:
            break
        mass = r[active]
        p[active] += alpha * mass
        r[active] = 0.0
        r += (1 - alpha) * (Pc[:, active] @ mass)
    p += r                                  # sub-eps residual settles in place
    total = p.sum()
    return p / total if total > 0 else p
