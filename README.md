# NexusRank

Graph-aware people search over a synthetic professional network. A text query is
turned into a **weighted seed set over concept nodes** (skills, companies,
schools), a **query-conditioned Personalized PageRank** is run from those seeds
across a heterogeneous graph, and the walk score is fused with BM25 text
relevance. Every result ships with the **evidence path** that earned it, and
clicking a result highlights that path in the live Sigma.js graph.

![stack](https://img.shields.io/badge/stack-FastAPI%20%C2%B7%20SciPy%20%C2%B7%20React%20%C2%B7%20Sigma.js-4c8dff)

## Quickstart

```bash
./run.sh            # UI: http://localhost:5173   API docs: http://localhost:8000/docs
```

First run creates the venv, installs deps, generates `backend/nexus.db`
(~330 nodes / ~1.7k edges) and starts both servers. Delete the `.db` file to
regenerate the dataset.

Manual equivalent:

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/uvicorn nexusrank.api:app --port 8000
cd frontend && npm install && npm run dev
```

## How ranking works

1. **Seeds** — BM25 over every node's text; matches are re-weighted by node type
   (`engine.SEED_BOOST`), because a *skill* node is a far better random-walk
   source than a person whose profile happens to repeat the query terms. With a
   `viewer` selected, half the restart mass goes to that person, so results are
   ranked relative to their corner of the network.
2. **Propagate** — the typed graph is collapsed into one symmetric,
   column-stochastic sparse operator; relation priors (`schema.EDGE_TYPES`)
   decide how much trust flows along `KNOWS` vs `STUDIED_AT`. PPR is solved
   either globally (`power_ppr`) or locally around the seeds (`local_ppr`,
   batched Andersen–Chung–Lang push).
3. **Fuse** — `score = graph_weight · norm(ppr) + (1 − graph_weight) · norm(bm25)`
   over candidates of the requested type. `graph_weight=0` gives pure lexical
   search, `1.0` pure structural — flip it via the API to see the difference.
4. **Explain** — Dijkstra with `cost = −log(weight)` returns the most probable
   seed→person chain, e.g. *Distributed Systems —skilled in→ Nadia Dubois
   —knows→ Greta Abadi*.

## Surface View

The canvas has two modes: **Network** (Sigma.js graph) and **Surface**, a 3D
*query-conditioned relevance field* built with three.js. Surface reuses the
existing fused scores — it never re-ranks. Each visible seed / top-10 person is
deposited as a Gaussian whose amplitude comes from its normalized fused score,
plus one synthetic query source at the score-weighted barycenter of the seeds.
The field is smoothed by solving the screened-Poisson equation
`u − λ∇²u = F` (64×64 grid, 60 Jacobi iterations, λ=0.015) and rendered as a
terrain where **height = query relevance**. The `QUERY: <query>` marker sits on
the dominant peak; seeds get rings, results are sized by score, edges are drawn
only between visible nodes. Clicking a ranked result highlights the same node on
the surface. Camera: orbit / zoom / reset.

Surface math tests: `cd frontend && npm test`.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/search?q=&viewer=&limit=&graph_weight=&solver=` | ranked people + scores + evidence path |
| `GET /api/graph?q=&viewer=&people=` | query-conditioned subgraph for the visualisation |
| `GET /api/viewers` | sample identities for the "search as…" selector |
| `GET /api/node/{id}` · `GET /api/health` | node lookup · graph size |

## Layout

```
backend/nexusrank/
  schema.py   node & edge types, relation priors
  store.py    GraphStore protocol + SQLiteStore   (swap-in point for Postgres/Neo4j)
  data.py     deterministic synthetic network with real community structure
  graph.py    CSR transition matrix, adjacency, path explanation
  ppr.py      power-iteration + local push PPR
  lexical.py  dependency-free BM25
  engine.py   seeds → PPR → fusion → explanations → subgraph
  api.py      FastAPI
frontend/src/ App.jsx (query bar, ranked list, score bars) · GraphView.jsx (Sigma)
```

Storage is behind the `GraphStore` protocol and ranking only ever sees
`Node`/`Edge` dataclasses, so moving to Postgres (or Neo4j for the adjacency)
means adding one class — no changes to the ranking or API layers.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

Covers graph math (column-stochasticity, symmetry, PPR is a distribution,
`alpha` controls locality, local ≈ global solver), path explanation, BM25,
fusion behaviour, viewer conditioning, and the HTTP endpoints.
