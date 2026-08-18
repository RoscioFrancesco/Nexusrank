"""Minimal BM25 lexical index over node text (no external deps)."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from .store import Node

_TOKEN = re.compile(r"[a-z0-9\+#]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25Index:
    def __init__(self, nodes: list[Node], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.ids = [n.id for n in nodes]
        docs = [tokenize(f"{n.name} {n.text}") for n in nodes]
        self.len = [len(d) or 1 for d in docs]
        self.avg = sum(self.len) / max(len(docs), 1)
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for term, tf in Counter(d).items():
                self.postings[term].append((i, tf))
        self.N = len(docs)

    def search(self, query: str, limit: int = 50) -> list[tuple[str, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            posting = self.postings.get(term)
            if not posting:
                continue
            idf = math.log(1 + (self.N - len(posting) + 0.5) / (len(posting) + 0.5))
            for i, tf in posting:
                norm = tf + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
                scores[i] += idf * tf * (self.k1 + 1) / norm
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        return [(self.ids[i], s) for i, s in ranked]
