"""Heterogeneous graph schema: node/edge types and their semantics.

Kept as plain data so the storage layer (SQLite today, Postgres/Neo4j later)
never needs to know about ranking, and ranking never needs to know about SQL.
"""
from __future__ import annotations

NODE_TYPES = ("person", "company", "skill", "school", "post")

# edge_type -> (src_type, dst_type, weight, symmetric)
# weight = how much trust/attention flows across this relation during PPR.
EDGE_TYPES: dict[str, tuple[str, str, float, bool]] = {
    "KNOWS":      ("person",  "person",  1.00, True),
    "WORKED_AT":  ("person",  "company", 0.70, True),
    "HAS_SKILL":  ("person",  "skill",   0.60, True),
    "STUDIED_AT": ("person",  "school",  0.45, True),
    "AUTHORED":   ("person",  "post",    0.35, True),
    "MENTIONS":   ("post",    "skill",   0.30, True),
    "REQUIRES":   ("company", "skill",   0.25, True),
}

EDGE_LABELS = {
    "KNOWS": "knows",
    "WORKED_AT": "worked at",
    "HAS_SKILL": "skilled in",
    "STUDIED_AT": "studied at",
    "AUTHORED": "authored",
    "MENTIONS": "mentions",
    "REQUIRES": "hires for",
}
