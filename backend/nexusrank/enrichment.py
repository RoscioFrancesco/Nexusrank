"""Manual profile enrichment: normalized local records -> graph nodes/edges.

Everything stays in the existing SQLite store. Ranking math is untouched: this
module only adds nodes, edges and searchable text, which PPR/BM25 then consume.
No network access, no scraping, no automatic LinkedIn reads.
"""
from __future__ import annotations

import json
import csv
import hashlib
from io import StringIO
from datetime import datetime, timezone

from .store import Edge, Node, SQLiteStore

DDL = """
CREATE TABLE IF NOT EXISTS person_profile (
    person_id TEXT PRIMARY KEY, name TEXT NOT NULL, linkedin_url TEXT DEFAULT '',
    company TEXT DEFAULT '', position TEXT DEFAULT '', location TEXT DEFAULT '',
    connected_on TEXT DEFAULT '', notes TEXT DEFAULT '', base_text TEXT DEFAULT '', manual INTEGER DEFAULT 0,
    source_type TEXT DEFAULT 'manual', source_url TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_pref (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS enrichment_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
    kind TEXT NOT NULL, payload TEXT NOT NULL, source_type TEXT DEFAULT 'manual',
    source_url TEXT DEFAULT '', updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS enrichment_edge (
    person_id TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrichment_node (
    id TEXT PRIMARY KEY, person_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_item_person ON enrichment_item(person_id);
CREATE INDEX IF NOT EXISTS idx_eedge_person ON enrichment_edge(person_id);
"""

SECTIONS = ("education", "experience", "skills", "activities", "projects")

# kind -> (concept node type, relation type)
RELATION = {
    "education": ("school", "STUDIED_AT"),
    "field": ("field", "DEGREE_FIELD"),
    "experience": ("company", "WORKED_AT"),
    "skills": ("skill", "SKILLED_IN"),
    "activities": ("activity", "MEMBER_OF"),
    "projects": ("project", "WORKED_ON"),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def my_concept_id(ntype: str, label: str) -> str:
    return f"{ntype}:my:{slug(label)}"


def ensure_tables(store: SQLiteStore) -> None:
    store.conn.executescript(DDL)
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(person_profile)")}
    if "connected_on" not in cols:
        store.conn.execute("ALTER TABLE person_profile ADD COLUMN connected_on TEXT DEFAULT ''")
    _repair_user_dataset(store)


def _repair_user_dataset(store: SQLiteStore) -> None:
    with store.conn:
        store.conn.execute(
            "UPDATE nodes SET dataset='my' WHERE id IN (SELECT person_id FROM person_profile) "
            "OR id LIKE 'person:li:%' OR id LIKE 'person:m%'"
        )
        store.conn.execute(
            "UPDATE edges SET dataset='my' WHERE src IN (SELECT id FROM nodes WHERE dataset='my') "
            "OR dst IN (SELECT id FROM nodes WHERE dataset='my')"
        )
        store.conn.execute(
            "UPDATE nodes SET dataset='my' WHERE id IN ("
            "SELECT src FROM edges WHERE dataset='my' UNION SELECT dst FROM edges WHERE dataset='my')"
        )


# --------------------------------------------------------------------------- read


def get_profile(store: SQLiteStore, person_id: str) -> dict | None:
    ensure_tables(store)
    node = store.conn.execute(
        "SELECT name, text, meta FROM nodes WHERE id=? AND type='person'", (person_id,)
    ).fetchone()
    if node is None:
        return None
    row = store.conn.execute(
        "SELECT linkedin_url, company, position, location, connected_on, notes, manual,"
        " source_type, source_url, updated_at FROM person_profile WHERE person_id=?",
        (person_id,),
    ).fetchone()
    company, position = _split_headline(node[2])
    profile = {
        "id": person_id, "name": node[0], "linkedin_url": "", "company": company,
            "position": position, "location": "", "connected_on": "", "notes": "", "manual": False,
        "source_type": "demo", "source_url": "", "updated_at": "",
    }
    if row:
        profile |= {
            "linkedin_url": row[0], "company": row[1] or company,
            "position": row[2] or position, "location": row[3], "connected_on": row[4],
            "notes": row[5], "manual": bool(row[6]), "source_type": row[7],
            "source_url": row[8], "updated_at": row[9],
        }
    sections = (_sections_from_graph(store, person_id, position)
                if row is None else {s: [] for s in SECTIONS})
    for kind, payload in store.conn.execute(
        "SELECT kind, payload FROM enrichment_item WHERE person_id=? ORDER BY id",
        (person_id,),
    ):
        sections.setdefault(kind, []).append(json.loads(payload))
    profile["sections"] = sections
    profile["enriched"] = any(sections[s] for s in SECTIONS)
    return profile


def _sections_from_graph(store: SQLiteStore, person_id: str, position: str = "") -> dict:
    sections = {s: [] for s in SECTIONS}
    seen: set[tuple[str, str]] = set()
    rows = store.conn.execute(
        "SELECT e.type, n.name, n.text, n.meta FROM edges e "
        "JOIN nodes n ON n.id=e.dst WHERE e.src=? ORDER BY e.type,n.name",
        (person_id,),
    ).fetchall()
    for rel, name, text, meta in rows:
        key = (rel, name)
        if key in seen:
            continue
        seen.add(key)
        if rel == "WORKED_AT":
            sections["experience"].append({"organization": name, "title": position,
                                           "start": "", "end": ""})
        elif rel == "STUDIED_AT":
            sections["education"].append({"institution": name, "degree": "",
                                          "field": "", "start_year": "", "end_year": ""})
        elif rel in {"HAS_SKILL", "SKILLED_IN"}:
            sections["skills"].append({"name": name})
        elif rel == "MEMBER_OF":
            sections["activities"].append({"organization": name, "role": meta or ""})
        elif rel == "WORKED_ON":
            sections["projects"].append({"title": name, "description": text or ""})
    return sections


def _split_headline(meta: str) -> tuple[str, str]:
    head = (meta or "").split(" · ")[0]
    if " at " in head:
        position, company = head.split(" at ", 1)
        return company.strip(), position.strip()
    return "", head.strip()


# -------------------------------------------------------------------------- write


def save_profile(store: SQLiteStore, person_id: str, payload: dict) -> dict:
    """Replace this person's manual records and regenerate their graph facts."""
    ensure_tables(store)
    base = store.conn.execute(
        "SELECT name, text, meta FROM nodes WHERE id=? AND type='person'", (person_id,)
    ).fetchone()
    if base is None:
        raise KeyError(person_id)

    kept = store.conn.execute(
        "SELECT base_text, manual, source_type FROM person_profile WHERE person_id=?", (person_id,)
    ).fetchone()
    base_text = kept[0] if kept and kept[0] else base[1]
    manual = int(kept[1]) if kept else 0
    source_type = kept[2] if kept and kept[2] else "manual"
    stamp = now()
    url = (payload.get("linkedin_url") or "").strip()
    name = (payload.get("name") or base[0]).strip()

    _clear_derived(store, person_id)
    with store.conn:
        store.conn.execute(
            "INSERT OR REPLACE INTO person_profile "
            "(person_id,name,linkedin_url,company,position,location,connected_on,notes,"
            "base_text,manual,source_type,source_url,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (person_id, name, url, (payload.get("company") or "").strip(),
             (payload.get("position") or "").strip(),
             (payload.get("location") or "").strip(),
             (payload.get("connected_on") or "").strip(),
             (payload.get("notes") or "").strip(), base_text, manual,
             source_type, url, stamp),
        )

    sections = payload.get("sections") or {}
    nodes: list[Node] = []
    edges: list[Edge] = []
    terms: list[str] = []

    def concept(kind: str, label: str, extra: str = "") -> str | None:
        label = (label or "").strip()
        if not label:
            return None
        ntype, rel = RELATION[kind]
        nid = my_concept_id(ntype, label)
        # reuse an identical institution / organization / skill if present
        if not store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (nid,)).fetchone():
            nodes.append(Node(nid, ntype, label, f"{label} {extra}".strip(), ntype))
            store.conn.execute("INSERT OR REPLACE INTO enrichment_node VALUES (?,?)",
                               (nid, person_id))
        edges.append(Edge(person_id, nid, rel))
        terms.append(label)
        return nid

    for row in sections.get("education", []):
        concept("education", row.get("institution", ""), row.get("field", ""))
        concept("field", row.get("field", ""))
        terms += [str(row.get(k, "")) for k in ("degree", "start_year", "end_year")]
    for row in sections.get("experience", []):
        concept("experience", row.get("organization", ""), row.get("title", ""))
        terms += [str(row.get(k, "")) for k in ("title", "start", "end")]
    for row in sections.get("skills", []):
        concept("skills", row.get("name", ""))
    for row in sections.get("activities", []):
        concept("activities", row.get("organization", ""), row.get("role", ""))
        terms.append(str(row.get("role", "")))
    for row in sections.get("projects", []):
        concept("projects", row.get("title", ""), row.get("description", ""))
        terms.append(str(row.get("description", "")))

    with store.conn:
        store.conn.executemany(
            "INSERT INTO enrichment_item (person_id, kind, payload, source_type,"
            " source_url, updated_at) VALUES (?,?,?,?,?,?)",
            [(person_id, kind, json.dumps(row), "manual", url, stamp)
             for kind in SECTIONS for row in sections.get(kind, []) if row],
        )
        store.conn.executemany(
            "INSERT INTO enrichment_edge VALUES (?,?,?,?)",
            [(person_id, e.src, e.dst, e.type) for e in edges],
        )
    store.write(nodes, edges, dataset="my")

    _write_person_node(store, person_id, name, base_text, payload, terms)
    set_pref(store, "active_dataset", "my")
    return get_profile(store, person_id)


def _write_person_node(store: SQLiteStore, person_id: str, name: str,
                       base_text: str, payload: dict, terms: list[str]) -> None:
    """Refresh the BM25 text so new concepts become query anchors."""
    extra = " ".join(t for t in terms if t)
    company = (payload.get("company") or "").strip()
    position = (payload.get("position") or "").strip()
    location = (payload.get("location") or "").strip()
    notes = (payload.get("notes") or "").strip()
    connected_on = (payload.get("connected_on") or "").strip()
    text = " ".join(x for x in (base_text, position, company, location, connected_on, extra, notes) if x)
    head = f"{position} at {company}" if position and company else (position or company)
    meta = " · ".join(x for x in (head, location) if x)
    with store.conn:
        store.conn.execute("UPDATE nodes SET name=?, text=?, meta=? WHERE id=?",
                           (name, text, meta, person_id))


def _clear_derived(store: SQLiteStore, person_id: str) -> None:
    """Drop this person's manual items, relations and now-orphaned concepts."""
    with store.conn:
        store.conn.executemany(
            "DELETE FROM edges WHERE src=? AND dst=? AND type=?",
            store.conn.execute(
                "SELECT src, dst, type FROM enrichment_edge WHERE person_id=?",
                (person_id,)).fetchall(),
        )
        store.conn.execute("DELETE FROM enrichment_edge WHERE person_id=?", (person_id,))
        store.conn.execute("DELETE FROM enrichment_item WHERE person_id=?", (person_id,))
        store.conn.execute(
            "DELETE FROM nodes WHERE id IN ("
            "  SELECT n.id FROM enrichment_node n WHERE n.person_id=? AND NOT EXISTS ("
            "    SELECT 1 FROM edges e WHERE e.src=n.id OR e.dst=n.id))",
            (person_id,),
        )
        store.conn.execute(
            "DELETE FROM enrichment_node WHERE person_id=? AND id NOT IN"
            " (SELECT id FROM nodes)", (person_id,))


def delete_enrichment(store: SQLiteStore, person_id: str) -> dict | None:
    """Remove manual data only. The person (CSV/demo or manual) is kept."""
    ensure_tables(store)
    row = store.conn.execute(
        "SELECT base_text FROM person_profile WHERE person_id=?", (person_id,)
    ).fetchone()
    _clear_derived(store, person_id)
    if row:
        with store.conn:
            store.conn.execute("UPDATE nodes SET text=? WHERE id=? AND ?<>''",
                               (row[0], person_id, row[0]))
            store.conn.execute(
                "UPDATE person_profile SET location='', notes='', updated_at=?"
                " WHERE person_id=?", (now(), person_id))
    return get_profile(store, person_id)


def add_person(store: SQLiteStore, payload: dict) -> dict:
    ensure_tables(store)
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    seq = store.conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE id LIKE 'person:m%'").fetchone()[0]
    person_id = f"person:m{seq:04d}"
    while store.conn.execute("SELECT 1 FROM nodes WHERE id=?", (person_id,)).fetchone():
        seq += 1
        person_id = f"person:m{seq:04d}"
    store.write([Node(person_id, "person", name, name, "")], [], dataset="my")
    with store.conn:
        store.conn.execute(
            "INSERT OR REPLACE INTO person_profile "
            "(person_id,name,linkedin_url,company,position,location,connected_on,notes,"
            "base_text,manual,source_type,source_url,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (person_id, name, (payload.get("linkedin_url") or "").strip(),
             (payload.get("company") or "").strip(),
             (payload.get("position") or "").strip(), "", "", "", name, 1,
             "manual", (payload.get("linkedin_url") or "").strip(), now()),
        )
    return save_profile(store, person_id, {**payload, "name": name})


def delete_person(store: SQLiteStore, person_id: str) -> bool:
    """Explicitly delete a contact: their node, every edge and all manual data.

    Clearing enrichment still never removes a person (see `delete_enrichment`);
    only this direct action does. Returns False when the person does not exist.
    """
    ensure_tables(store)
    row = store.conn.execute(
        "SELECT manual FROM person_profile WHERE person_id=?", (person_id,)).fetchone()
    if not row or not bool(row[0]):
        return False
    _clear_derived(store, person_id)
    with store.conn:
        store.conn.execute("DELETE FROM edges WHERE src=? OR dst=?",
                           (person_id, person_id))
        store.conn.execute("DELETE FROM nodes WHERE id=?", (person_id,))
        store.conn.execute("DELETE FROM person_profile WHERE person_id=?", (person_id,))
        store.conn.execute("DELETE FROM enrichment_node WHERE person_id=?", (person_id,))
        # posts authored by this person become orphans -> drop them too
        store.conn.execute(
            "DELETE FROM nodes WHERE type='post' AND id NOT IN"
            " (SELECT src FROM edges UNION SELECT dst FROM edges)")
    return True


def import_connections_csv(store: SQLiteStore, content: str) -> dict:
    ensure_tables(store)
    rows = _linkedin_rows(content)
    stamp = now()
    imported = 0
    people: list[tuple[str, str]] = []
    for r in rows:
        url = _pick(r, "URL", "Profile URL", "LinkedIn URL", "LinkedIn Profile")
        first = _pick(r, "First Name", "FirstName")
        last = _pick(r, "Last Name", "LastName")
        name = (_pick(r, "Name") or f"{first} {last}").strip()
        if not (url or name):
            continue
        pid = _linkedin_person_id(url or name)
        company = _pick(r, "Company")
        position = _pick(r, "Position")
        connected_on = _pick(r, "Connected On", "Connected")
        text = " ".join(x for x in (name, position, company, connected_on) if x)
        meta = " · ".join(x for x in ((f"{position} at {company}" if position and company else position or company), connected_on) if x)
        store.write([Node(pid, "person", name, text, meta)], [], dataset="my")
        edges: list[Edge] = []
        if company:
            cid = my_concept_id("company", company)
            store.write([Node(cid, "company", company, company, "company")], [], dataset="my")
            edges.append(Edge(pid, cid, "WORKED_AT"))
        store.write([], edges, dataset="my")
        people.append((pid, company))
        with store.conn:
            store.conn.execute(
                "INSERT OR REPLACE INTO person_profile "
                "(person_id,name,linkedin_url,company,position,location,connected_on,notes,"
                "base_text,manual,source_type,source_url,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, name, url, company, position, "", connected_on, "", text, 0,
                 "linkedin_csv", url, stamp),
            )
        imported += 1
    store.write([], _generated_contact_edges(people), dataset="my")
    set_pref(store, "active_dataset", "my")
    return {"rows": len(rows), "imported": imported, "people": my_network_count(store)}


def import_linkedin_export(store: SQLiteStore, files: list[dict]) -> dict:
    by_name = {_base_name(f.get("name", "")).lower(): f.get("content", "")
               for f in files if f.get("content")}
    connections = by_name.get("connections.csv")
    if not connections:
        raise ValueError("Connections.csv is required")
    out = import_connections_csv(store, connections)
    profile = _profile_payload(by_name)
    if profile:
        me = _save_me_profile(store, profile)
        imported = [r[0] for r in store.conn.execute(
            "SELECT person_id FROM person_profile WHERE source_type='linkedin_csv'"
        )]
        store.write([], [Edge(me, pid, "KNOWS", 1.0) for pid in imported], dataset="my")
        out["profile"] = me
        out["profile_items"] = sum(len(profile["sections"][k]) for k in SECTIONS)
        out["people"] = my_network_count(store)
    return out


def _base_name(path: str) -> str:
    return path.replace("\\", "/").split("/")[-1]


def _profile_payload(files: dict[str, str]) -> dict | None:
    profile = _rows(_file(files, "profile.csv"))
    p = profile[0] if profile else {}
    first = _pick(p, "First Name")
    last = _pick(p, "Last Name")
    name = (f"{first} {last}".strip() or "Me")
    sections = {s: [] for s in SECTIONS}
    notes = [_pick(p, "Summary"), _pick(p, "Industry")]
    for r in _rows(_file(files, "positions.csv")):
        org = _pick(r, "Company Name", "Company")
        title = _pick(r, "Title")
        if org or title:
            sections["experience"].append({
                "organization": org, "title": title,
                "start": _pick(r, "Started On", "Start Date"),
                "end": _pick(r, "Finished On", "End Date"),
            })
    for r in _rows(_file(files, "education.csv")):
        school = _pick(r, "School Name", "School")
        degree = _pick(r, "Degree Name", "Degree")
        if school or degree:
            sections["education"].append({
                "institution": school, "degree": degree,
                "field": _pick(r, "Notes"), "start_year": _pick(r, "Start Date"),
                "end_year": _pick(r, "End Date"),
            })
    for r in _rows(_file(files, "skills.csv")):
        skill = _pick(r, "Name", "Skill")
        if skill:
            sections["skills"].append({"name": skill})
    for r in _rows(_file(files, "certifications.csv")):
        cert = _pick(r, "Name")
        if cert:
            sections["projects"].append({
                "title": cert,
                "description": " ".join(x for x in (
                    _pick(r, "Authority"), _pick(r, "Started On"),
                    _pick(r, "Finished On"), _pick(r, "License Number")) if x),
            })
    for r in _rows(_file(files, "company follows.csv")):
        org = _pick(r, "Organization")
        if org:
            sections["activities"].append({"organization": org, "role": "followed company"})
    for r in _rows(_file_prefix(files, "member_follows_")):
        full_name = _pick(r, "FullName", "Name")
        if full_name:
            sections["activities"].append({"organization": full_name, "role": "followed member"})
    for r in _rows(_file(files, "rich_media.csv")):
        link = _pick(r, "Media Link")
        if link:
            sections["projects"].append({
                "title": _pick(r, "Media Description") or "LinkedIn media",
                "description": " ".join(x for x in (_pick(r, "Date/Time"), link) if x),
            })
    for r in _rows(_file_prefix(files, "saved_items_")):
        item = _pick(r, "savedItem")
        if item:
            sections["projects"].append({
                "title": "Saved LinkedIn item",
                "description": " ".join(x for x in (item, _pick(r, "CreatedTime")) if x),
            })
    for r in _rows(_file(files, "inferences_about_you.csv")):
        inf = _pick(r, "Inference")
        typ = _pick(r, "Type of inference")
        if inf and typ:
            notes.append(f"{typ}: {inf}")
    if not any(sections[s] for s in SECTIONS) and name == "Me":
        return None
    return {
        "name": name, "company": "", "position": _pick(p, "Headline"),
        "location": _pick(p, "Geo Location"), "notes": " | ".join(n for n in notes if n),
        "sections": sections,
    }


def _file(files: dict[str, str], name: str) -> str:
    return files.get(name.lower(), "")


def _file_prefix(files: dict[str, str], prefix: str) -> str:
    prefix = prefix.lower()
    for name, content in files.items():
        if name.startswith(prefix):
            return content
    return ""


def _save_me_profile(store: SQLiteStore, payload: dict) -> str:
    person_id = "person:me"
    store.write([Node(person_id, "person", payload["name"], payload["name"], "You")],
                [], dataset="my")
    with store.conn:
        store.conn.execute(
            "INSERT OR REPLACE INTO person_profile "
            "(person_id,name,linkedin_url,company,position,location,connected_on,notes,"
            "base_text,manual,source_type,source_url,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (person_id, payload["name"], "", "", payload.get("position", ""),
             payload.get("location", ""), "", payload.get("notes", ""),
             payload["name"], 1, "linkedin_export", "", now()),
        )
    save_profile(store, person_id, payload)
    return person_id


def _linkedin_rows(content: str) -> list[dict]:
    lines = content.lstrip("\ufeff").splitlines()
    start = 0
    for i, line in enumerate(lines):
        low = line.lower()
        if ("first name" in low and "last name" in low) or ("url" in low and "company" in low):
            start = i
            break
    text = "\n".join(lines[start:])
    for dialect in _dialects(text):
        rows = list(csv.DictReader(StringIO(text), dialect=dialect))
        if rows and any(_pick(r, "URL", "Profile URL", "LinkedIn URL", "LinkedIn Profile", "Name", "First Name") for r in rows):
            return rows
    return []


def _rows(content: str) -> list[dict]:
    if not content.strip():
        return []
    text = content.lstrip("\ufeff")
    for delim in (",", ";", "\t"):
        dialect = csv.excel()
        dialect.delimiter = delim
        rows = list(csv.DictReader(StringIO(text), dialect=dialect))
        if rows and rows[0]:
            return rows
    return []


def _dialects(text: str):
    try:
        yield csv.Sniffer().sniff(text[:4096])
    except csv.Error:
        pass
    for delim in (",", ";", "\t"):
        d = csv.excel()
        d.delimiter = delim
        yield d


def _generated_contact_edges(people: list[tuple[str, str]]) -> list[Edge]:
    edges: list[Edge] = []
    by_company: dict[str, list[str]] = {}
    for pid, company in people:
        by_company.setdefault(company.lower().strip(), []).append(pid)
    for group in by_company.values():
        if len(group) < 2:
            continue
        for i, pid in enumerate(group):
            edges.append(Edge(pid, group[(i + 1) % len(group)], "KNOWS", 0.7))
    ids = [p for p, _ in people]
    for i in range(len(ids) - 1):
        edges.append(Edge(ids[i], ids[i + 1], "KNOWS", 0.35))
    return edges


def _pick(row: dict, *keys: str) -> str:
    lower = {str(k).lower().strip(): v for k, v in row.items() if k is not None}
    for k in keys:
        v = lower.get(k.lower())
        if v:
            return str(v).strip()
    return ""


def _linkedin_person_id(stable: str) -> str:
    h = hashlib.sha1(stable.strip().lower().encode()).hexdigest()[:16]
    return f"person:li:{h}"


def my_network_count(store: SQLiteStore) -> int:
    ensure_tables(store)
    return store.conn.execute(
        "SELECT COUNT(*) FROM person_profile WHERE source_type IN "
        "('linkedin_csv','manual','linkedin_export') OR manual=1"
    ).fetchone()[0]


def imported_network_count(store: SQLiteStore) -> int:
    ensure_tables(store)
    return store.conn.execute(
        "SELECT COUNT(*) FROM person_profile WHERE source_type='linkedin_csv' OR person_id LIKE 'person:li:%'"
    ).fetchone()[0]


def get_pref(store: SQLiteStore, key: str, default: str = "") -> str:
    ensure_tables(store)
    row = store.conn.execute("SELECT value FROM app_pref WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_pref(store: SQLiteStore, key: str, value: str) -> None:
    ensure_tables(store)
    with store.conn:
        store.conn.execute("INSERT OR REPLACE INTO app_pref VALUES (?,?)", (key, value))


def clear_my_network(store: SQLiteStore) -> int:
    ensure_tables(store)
    ids = [r[0] for r in store.conn.execute(
        "SELECT person_id FROM person_profile WHERE "
        "source_type='linkedin_csv' OR person_id LIKE 'person:li:%' "
        "OR manual=1 OR person_id LIKE 'person:m%'"
    )]
    for pid in ids:
        _clear_derived(store, pid)
    with store.conn:
        store.conn.executemany("DELETE FROM edges WHERE src=? OR dst=?", [(i, i) for i in ids])
        store.conn.executemany("DELETE FROM nodes WHERE id=?", [(i,) for i in ids])
        store.conn.execute(
            "DELETE FROM person_profile WHERE source_type='linkedin_csv' "
            "OR person_id LIKE 'person:li:%' OR manual=1 OR person_id LIKE 'person:m%'"
        )
        store.conn.execute(
            "DELETE FROM enrichment_item WHERE person_id NOT IN (SELECT person_id FROM person_profile)"
        )
        store.conn.execute(
            "DELETE FROM enrichment_edge WHERE person_id NOT IN (SELECT person_id FROM person_profile)"
        )
        store.conn.execute(
            "DELETE FROM enrichment_node WHERE person_id NOT IN (SELECT person_id FROM person_profile)"
        )
        store.conn.execute("DELETE FROM nodes WHERE type='company' AND id NOT IN (SELECT src FROM edges UNION SELECT dst FROM edges)")
    set_pref(store, "active_dataset", "demo")
    return len(ids)
