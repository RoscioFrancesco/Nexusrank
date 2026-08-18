"""FastAPI surface. Seeds the SQLite store on first boot, then serves search."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import data
from .engine import NexusRank
from .store import SQLiteStore

DB_PATH = os.environ.get("NEXUSRANK_DB", "nexus.db")
N_PEOPLE = int(os.environ.get("NEXUSRANK_PEOPLE", "180"))

app = FastAPI(title="NexusRank", version="0.1.0",
              description="Query-conditioned Personalized PageRank over a "
                          "heterogeneous professional network.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

_engine: NexusRank | None = None


def engine() -> NexusRank:
    global _engine
    if _engine is None:
        store = SQLiteStore(DB_PATH)
        if store.is_empty():
            data.generate(store, n_people=N_PEOPLE)
        _engine = NexusRank(store)
    return _engine


@app.get("/api/health")
def health() -> dict:
    e = engine()
    return {"status": "ok", "nodes": len(e.graph), "edges": int(e.graph.A.nnz // 2)}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), viewer: str | None = None,
           limit: int = 10, graph_weight: float = 0.75,
           solver: str = "local") -> dict:
    return engine().rank(q, viewer=viewer, limit=limit,
                         graph_weight=graph_weight, solver=solver).to_dict()


@app.get("/api/graph")
def graph(q: str = Query(..., min_length=1), viewer: str | None = None,
          people: int = 24) -> dict:
    return engine().subgraph(q, viewer=viewer, people=people)


@app.get("/api/viewers")
def viewers(limit: int = 12) -> dict:
    e = engine()
    ids = e.graph.ids_of_type("person")[:limit]
    return {"viewers": [{"id": i, "name": e.graph.by_id[i].name,
                         "meta": e.graph.by_id[i].meta} for i in ids]}


@app.get("/api/node/{node_id}")
def node(node_id: str) -> dict:
    e = engine()
    n = e.graph.by_id.get(node_id)
    if n is None:
        raise HTTPException(404, "unknown node")
    return {"id": n.id, "name": n.name, "type": n.type, "meta": n.meta,
            "degree": len(e.graph.adj.get(node_id, ()))}


# Optional: serve the built SPA so the demo is one process.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")
