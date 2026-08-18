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
    text TEXT DEFAULT '', meta TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL,
    weight REAL DEFAULT 1.0, PRIMARY KEY (src, dst, type)
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
"""


class SQLiteStore:
    """File-backed by default; pass ':memory:' for tests."""

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(DDL)

    def write(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?)",
                [(n.id, n.type, n.name, n.text, n.meta) for n in nodes],
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO edges VALUES (?,?,?,?)",
                [(e.src, e.dst, e.type, e.weight) for e in edges],
            )

    def nodes(self) -> list[Node]:
        rows = self.conn.execute(
            "SELECT id,type,name,text,meta FROM nodes ORDER BY id"
        ).fetchall()
        return [Node(*r) for r in rows]

    def edges(self) -> list[Edge]:
        rows = self.conn.execute(
            "SELECT src,dst,type,weight FROM edges ORDER BY src,dst,type"
        ).fetchall()
        return [Edge(*r) for r in rows]

    def is_empty(self) -> bool:
        return self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 0
