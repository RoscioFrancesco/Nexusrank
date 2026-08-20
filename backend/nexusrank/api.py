"""FastAPI surface. Seeds the SQLite store on first boot, then serves search."""
from __future__ import annotations

import os
import re
import secrets
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import data, enrichment
from .engine import NexusRank
from .store import SQLiteStore

DB_PATH = os.environ.get("NEXUSRANK_DB", "nexus.db")
TOKEN = os.environ.get("NEXUSRANK_TOKEN") or secrets.token_urlsafe(32)
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}
ALLOWED_ORIGINS = set(filter(None, os.environ.get(
    "NEXUSRANK_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173,"
    "http://127.0.0.1:8000,http://localhost:8000,http://testserver",
).split(",")))

app = FastAPI(title="NexusRank", version="0.1.0",
              description="Query-conditioned Personalized PageRank over a "
                          "heterogeneous professional network.",
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS),
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type", "X-NexusRank-Token"])

_engine: NexusRank | None = None


def _origin_of(value: str | None) -> str:
    if not value:
        return ""
    p = urlsplit(value)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else value


def _host(value: str | None) -> str:
    if not value:
        return ""
    return value.rsplit("@", 1)[-1].split(":", 1)[0].strip("[]").lower()


@app.middleware("http")
async def local_only_guard(request, call_next):
    path = request.url.path
    host = _host(request.headers.get("host"))
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "local host only"}, status_code=403)
    origin = _origin_of(request.headers.get("origin"))
    referer = _origin_of(request.headers.get("referer"))
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "origin not allowed"}, status_code=403)
    if referer and referer not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "referer not allowed"}, status_code=403)
    if path.startswith("/api"):
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "cross-site requests blocked"}, status_code=403)
        if request.method != "OPTIONS" and path not in {"/api/client-token", "/api/health"}:
            if request.headers.get("x-nexusrank-token") != TOKEN:
                return JSONResponse({"detail": "invalid local token"}, status_code=403)
    return await call_next(request)


def engine() -> NexusRank:
    global _engine
    if _engine is None:
        store = SQLiteStore(DB_PATH)
        enrichment.ensure_tables(store)
        data.ensure_manhattan_demo(store)
        pref = enrichment.get_pref(store, "active_dataset", "")
        mine = enrichment.my_network_count(store)
        if mine and not pref:
            enrichment.set_pref(store, "active_dataset", "my")
        if pref == "my" and not mine:
            enrichment.set_pref(store, "active_dataset", "demo")
        _engine = NexusRank(store)
    return _engine


def _reindex() -> NexusRank:
    """Rebuild graph + BM25 after a write, so new concepts are query anchors."""
    global _engine
    _engine = NexusRank(engine().store)
    return _engine


STOP = {"and", "the", "for", "with", "at", "in", "of", "to", "a", "an", "on",
        "systems", "engineer", "lead", "manager", "intern", "company"}


def _suggestions(e: NexusRank, limit: int = 12) -> list[str]:
    boosts = {"skill": 5, "field": 4, "school": 3, "company": 2,
              "project": 2, "activity": 1}
    scored = []
    for n in e.graph.nodes:
        if n.type in boosts:
            degree = len(e.graph.adj.get(n.id, ()))
            if degree == 0:
                continue
            scored.append((boosts[n.type] * 10 + degree, n.name))
    if scored:
        seen, out = set(), []
        for _, name in sorted(scored, reverse=True):
            k = name.lower()
            if k not in seen:
                seen.add(k)
                out.append(name)
            if len(out) == limit:
                return out
    words = Counter()
    for n in e.graph.nodes:
        if n.type == "person":
            words.update(w for w in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", n.text.lower())
                         if w not in STOP)
    return [w for w, _ in words.most_common(limit)]


def _people(e: NexusRank, q: str, limit: int = 20) -> list[dict]:
    terms = [t.lower() for t in q.split() if t.strip()]
    out = []
    for n in e.graph.nodes:
        if n.type != "person":
            continue
        hay = f"{n.name} {n.meta} {n.text}".lower()
        if terms and not all(t in hay for t in terms):
            continue
        score = (20 if q and n.name.lower().startswith(q.lower()) else 0)
        score += sum(hay.count(t) for t in terms)
        out.append((score, n))
    out.sort(key=lambda x: (-x[0], x[1].name))
    return [{"id": n.id, "name": n.name, "meta": n.meta} for _, n in out[:limit]]


@app.get("/api/health")
def health() -> dict:
    e = engine()
    mine = enrichment.my_network_count(e.store)
    imported = enrichment.imported_network_count(e.store)
    dataset = enrichment.get_pref(e.store, "active_dataset", "my" if mine else "demo")
    return {"status": "ok", "nodes": len(e.graph), "edges": int(e.graph.A.nnz // 2),
            "my_network": mine, "imported_network": imported, "active_dataset": dataset}


@app.get("/api/client-token")
def client_token() -> dict:
    return {"token": TOKEN}


@app.get("/api/state")
def state() -> dict:
    e = engine()
    mine = enrichment.my_network_count(e.store)
    imported = enrichment.imported_network_count(e.store)
    dataset = enrichment.get_pref(e.store, "active_dataset", "my" if mine else "demo")
    return {"active_dataset": dataset, "my_network": mine, "imported_network": imported}


@app.get("/api/suggestions")
def suggestions(limit: int = 12) -> dict:
    return {"suggestions": _suggestions(engine(), limit)}


@app.get("/api/people")
def people(q: str = "", limit: int = 20) -> dict:
    return {"people": _people(engine(), q, limit)}


@app.put("/api/state")
def put_state(payload: dict = Body(...)) -> dict:
    dataset = payload.get("active_dataset")
    if dataset not in {"demo", "my"}:
        raise HTTPException(422, "active_dataset must be demo or my")
    enrichment.set_pref(engine().store, "active_dataset", dataset)
    _reindex()
    return state()


@app.post("/api/import/linkedin")
def import_linkedin(payload: dict = Body(...)) -> dict:
    content = payload.get("content") or ""
    files = payload.get("files") or []
    if not content.strip() and not files:
        raise HTTPException(422, "content or files are required")
    try:
        out = (enrichment.import_linkedin_export(engine().store, files)
               if files else enrichment.import_connections_csv(engine().store, content))
    except Exception as exc:
        raise HTTPException(422, f"CSV import failed: {exc}") from exc
    if out["imported"] == 0:
        raise HTTPException(422, "no LinkedIn contacts found in CSV")
    _reindex()
    return out


@app.post("/api/my-network/clear")
def clear_my_network(payload: dict = Body(...)) -> dict:
    if payload.get("confirm") is not True:
        raise HTTPException(422, "confirmation required")
    deleted = enrichment.clear_my_network(engine().store)
    _reindex()
    return {"deleted": deleted}


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


# ---- manual profile enrichment (local only) --------------------------------


@app.get("/api/person/{person_id}/profile")
def get_profile(person_id: str) -> dict:
    prof = enrichment.get_profile(engine().store, person_id)
    if prof is None:
        raise HTTPException(404, "unknown person")
    return prof


@app.put("/api/person/{person_id}/profile")
def put_profile(person_id: str, payload: dict = Body(...)) -> dict:
    try:
        prof = enrichment.save_profile(engine().store, person_id, payload)
    except KeyError:
        raise HTTPException(404, "unknown person")
    _reindex()
    return prof


@app.delete("/api/person/{person_id}/enrichment")
def delete_enrichment(person_id: str) -> dict:
    prof = enrichment.delete_enrichment(engine().store, person_id)
    if prof is None:
        raise HTTPException(404, "unknown person")
    _reindex()
    return prof


@app.post("/api/person")
def post_person(payload: dict = Body(...)) -> dict:
    try:
        prof = enrichment.add_person(engine().store, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _reindex()
    return prof


@app.delete("/api/person/{person_id}")
def delete_person(person_id: str) -> dict:
    if not enrichment.delete_person(engine().store, person_id):
        raise HTTPException(403, "only manually-created people can be deleted")
    _reindex()
    return {"deleted": person_id}


# Optional: serve the built SPA so the demo is one process.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")
