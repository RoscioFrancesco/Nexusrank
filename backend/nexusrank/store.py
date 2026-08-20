"""Storage interface + SQLite implementation.

`GraphStore` is the only contract the rest of the app depends on, so swapping in
Postgres/Neo4j means writing one more class, not touching ranking or the API.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    type: str
    name: str
    text: str = ""      # searchable blob (headline, description, body)
    meta: str = ""      # small display string (e.g. location / title)


@dataclass(frozen=True, slots=True)
class Edge:
    src: str
    dst: str
    type: str
    weight: float = 1.0


class GraphStore(Protocol):
    def write(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None: ...
    def nodes(self) -> list[Node]: ...
    def edges(self) -> list[Edge]: ...


DDL = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
    text TEXT DEFAULT '', meta TEXT DEFAULT '', dataset TEXT DEFAULT 'demo'
);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL,
    weight REAL DEFAULT 1.0, dataset TEXT DEFAULT 'demo', PRIMARY KEY (src, dst, type)
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
"""


class SQLiteStore:
    """File-backed by default; pass ':memory:' for tests."""

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(DDL)
        self._migrate()

    def _migrate(self) -> None:
        ncols = {r[1] for r in self.conn.execute("PRAGMA table_info(nodes)")}
        ecols = {r[1] for r in self.conn.execute("PRAGMA table_info(edges)")}
        with self.conn:
            if "dataset" not in ncols:
                self.conn.execute("ALTER TABLE nodes ADD COLUMN dataset TEXT DEFAULT 'demo'")
            if "dataset" not in ecols:
                self.conn.execute("ALTER TABLE edges ADD COLUMN dataset TEXT DEFAULT 'demo'")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_dataset ON nodes(dataset)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_dataset ON edges(dataset)")

    def active_dataset(self) -> str:
        table = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_pref'"
        ).fetchone()
        if not table:
            return "demo"
        row = self.conn.execute(
            "SELECT value FROM app_pref WHERE key='active_dataset'"
        ).fetchone()
        return row[0] if row and row[0] in {"demo", "my"} else "demo"

    def write(self, nodes: Iterable[Node], edges: Iterable[Edge],
              dataset: str = "demo") -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO nodes (id,type,name,text,meta,dataset)"
                " VALUES (?,?,?,?,?,?)",
                [(n.id, n.type, n.name, n.text, n.meta, dataset) for n in nodes],
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO edges (src,dst,type,weight,dataset)"
                " VALUES (?,?,?,?,?)",
                [(e.src, e.dst, e.type, e.weight, dataset) for e in edges],
            )

    def nodes(self) -> list[Node]:
        dataset = self.active_dataset()
        rows = self.conn.execute(
            "SELECT id,type,name,text,meta FROM nodes WHERE dataset=? ORDER BY id",
            (dataset,),
        ).fetchall()
        return [Node(*r) for r in rows]

    def edges(self) -> list[Edge]:
        dataset = self.active_dataset()
        rows = self.conn.execute(
            "SELECT src,dst,type,weight FROM edges WHERE dataset=? ORDER BY src,dst,type",
            (dataset,),
        ).fetchall()
        return [Edge(*r) for r in rows]

    def is_empty(self) -> bool:
        return self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 0

    def dataset_count(self, dataset: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE dataset=?", (dataset,)
        ).fetchone()[0]

    def demo_people_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE dataset='demo' AND type='person'"
        ).fetchone()[0]
