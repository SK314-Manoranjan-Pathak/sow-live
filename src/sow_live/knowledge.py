"""Personal knowledge graph: one SQLite file at ~/.sow-live/knowledge.db.

Nodes: engagements, sessions, facts (brief fields), verified answers, open questions,
flags, entities (systems, AWS services, constraints, solution tags, industries).
Edges: engagement -> entity (uses / integrates / constrained_by / tagged ...).

Used for:
  - follow-up calls: carry the same customer's earlier fields and open questions forward;
  - verified answers: reuse AWS/wiki answers checked on earlier calls (with their age);
  - the `sow-knowledge` MCP server, so Kiro can query it any time.
It is personal: nothing leaves this machine.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import KNOWLEDGE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS engagements (
  slug TEXT PRIMARY KEY, client TEXT, project TEXT, path TEXT, created TEXT, industry TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, slug TEXT, started_at TEXT, summary TEXT,
  critical_filled INTEGER, critical_total INTEGER, transcript_lines INTEGER
);
CREATE TABLE IF NOT EXISTS facts (
  slug TEXT, field_id TEXT, label TEXT, value TEXT, status TEXT, evidence TEXT, session_id TEXT, updated_at TEXT,
  PRIMARY KEY (slug, field_id)
);
CREATE TABLE IF NOT EXISTS answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, label TEXT, query TEXT, headline TEXT, detail TEXT,
  confidence TEXT, sources TEXT, sow_impact TEXT, follow_up TEXT, checked_at TEXT, slug TEXT, session_id TEXT,
  lookup_id TEXT, UNIQUE (session_id, lookup_id)
);
CREATE TABLE IF NOT EXISTS open_questions (
  slug TEXT, qid TEXT, text TEXT, why TEXT, priority INTEGER, session_id TEXT, PRIMARY KEY (slug, qid)
);
CREATE TABLE IF NOT EXISTS flags (
  slug TEXT, fid TEXT, text TEXT, learning TEXT, session_id TEXT, PRIMARY KEY (slug, fid)
);
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, UNIQUE (name, type)
);
CREATE TABLE IF NOT EXISTS edges (
  slug TEXT, entity_id INTEGER, relation TEXT, session_id TEXT, PRIMARY KEY (slug, entity_id, relation)
);
"""

FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS answers_fts USING fts5(
  label, query, headline, detail, content='answers', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS answers_ai AFTER INSERT ON answers BEGIN
  INSERT INTO answers_fts(rowid, label, query, headline, detail) VALUES (new.id, new.label, new.query, new.headline, new.detail);
END;
CREATE TRIGGER IF NOT EXISTS answers_ad AFTER DELETE ON answers BEGIN
  INSERT INTO answers_fts(answers_fts, rowid, label, query, headline, detail) VALUES ('delete', old.id, old.label, old.query, old.headline, old.detail);
END;
"""

STOP = set("""a an and are as at be but by can do does for from has have how i if in into is it its of on or our so
that the their them then there these they this to too us was we what when where which who will with would you your
yes no not okay ok like just about also any some more most very really want need get one two all""".split())


@contextmanager
def connect(db: Path = KNOWLEDGE_DB):
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db), timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        con.executescript(FTS)
    except sqlite3.OperationalError:
        pass  # FTS5 missing: search falls back to LIKE
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _has_fts(con) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE name='answers_fts'").fetchone() is not None


def _terms(text: str, limit: int = 24) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    seen, out = set(), []
    for w in words:
        if w not in STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:limit]


def _age_days(ts: str) -> int:
    try:
        return max(0, (datetime.now() - datetime.fromisoformat(ts)).days)
    except (TypeError, ValueError):
        return 9999


# ------------------------------------------------------------------ ingest
def ingest_session(engagement, session) -> dict:
    """Store a finished session. Safe to call again (upserts)."""
    st = session.state
    sid = session.path.name
    now = datetime.now().isoformat(timespec="seconds")
    cf, ct, _, _ = session.coverage()
    counts = {"facts": 0, "answers": 0, "entities": 0}
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO engagements VALUES (?,?,?,?,?,?)",
                    (engagement.slug, engagement.client, engagement.project, str(engagement.path),
                     engagement.meta.get("created", ""),
                     (st["fields"].get("industry") or {}).get("value", "") or st.get("industry", "")))
        con.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?)",
                    (sid, engagement.slug, st["started_at"], st.get("summary", ""), cf, ct, st["transcript_count"]))
        for fid, rec in st["fields"].items():
            if rec.get("status") == "previous_call":
                continue  # unchanged carry-over
            label = session.catalog_by_id.get(fid, {}).get("label", fid)
            con.execute("INSERT OR REPLACE INTO facts VALUES (?,?,?,?,?,?,?,?)",
                        (engagement.slug, fid, label, rec["value"], rec.get("status", ""), rec.get("evidence", ""),
                         sid, now))
            counts["facts"] += 1
        for l in st["lookups"]:
            if l["state"] != "done" or l.get("cached") or l["kind"] == "learnings_refresh":
                continue
            a = l.get("answer") or {}
            if a.get("confidence") not in ("confirmed", "partial", "found"):
                continue  # only keep answers that were actually verified
            con.execute(
                "INSERT OR IGNORE INTO answers (kind,label,query,headline,detail,confidence,sources,sow_impact,"
                "follow_up,checked_at,slug,session_id,lookup_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (l["kind"], l.get("label", ""), l["query"], a.get("headline", ""), json.dumps(a.get("detail", [])),
                 a.get("confidence", ""), json.dumps(a.get("sources", [])), a.get("sow_impact", ""),
                 a.get("follow_up_question", ""), l.get("answered_at", now), engagement.slug, sid, l["id"]))
            counts["answers"] += 1
        con.execute("DELETE FROM open_questions WHERE slug=?", (engagement.slug,))
        for q in st["questions"]:
            if q["state"] in ("open", "asked"):
                con.execute("INSERT OR REPLACE INTO open_questions VALUES (?,?,?,?,?,?)",
                            (engagement.slug, q["id"], q["text"], q.get("why", ""), q.get("priority", 2), sid))
        for f in st["flags"]:
            con.execute("INSERT OR REPLACE INTO flags VALUES (?,?,?,?,?)",
                        (engagement.slug, f["id"], f["text"], f.get("learning", ""), sid))
        for ent in st.get("entities") or []:
            name, typ = (ent.get("name") or "").strip(), (ent.get("type") or "").strip().lower()
            if not name or not typ:
                continue
            con.execute("INSERT OR IGNORE INTO entities (name, type) VALUES (?,?)", (name, typ))
            eid = con.execute("SELECT id FROM entities WHERE name=? AND type=?", (name, typ)).fetchone()["id"]
            con.execute("INSERT OR REPLACE INTO edges VALUES (?,?,?,?)",
                        (engagement.slug, eid, ent.get("relation", "mentions"), sid))
            counts["entities"] += 1
    return counts


# ------------------------------------------------------------------ queries used during calls
def previous_calls(slug: str) -> dict:
    with connect() as con:
        sessions = [dict(r) for r in con.execute(
            "SELECT id, started_at, summary, critical_filled, critical_total FROM sessions WHERE slug=? "
            "ORDER BY started_at", (slug,))]
        facts = {r["field_id"]: dict(r) for r in con.execute(
            "SELECT field_id, value, status, evidence, updated_at FROM facts WHERE slug=?", (slug,))}
        questions = [dict(r) for r in con.execute(
            "SELECT qid AS id, text, why, priority FROM open_questions WHERE slug=? ORDER BY priority", (slug,))]
        flags = [dict(r) for r in con.execute("SELECT fid AS id, text, learning FROM flags WHERE slug=?", (slug,))]
    return {"sessions": sessions, "facts": facts, "questions": questions, "flags": flags}


def known_answers(text: str, limit: int = 6, kinds: tuple[str, ...] | None = None) -> list[dict]:
    terms = _terms(text)
    if not terms:
        return []
    with connect() as con:
        if _has_fts(con):
            match = " OR ".join(f'"{t}"' for t in terms)
            sql = ("SELECT a.*, bm25(answers_fts) AS rank FROM answers_fts JOIN answers a ON a.id = answers_fts.rowid "
                   "WHERE answers_fts MATCH ? ORDER BY rank LIMIT ?")
            rows = con.execute(sql, (match, limit * 3)).fetchall()
        else:
            like = " OR ".join("(a.query LIKE ? OR a.headline LIKE ?)" for _ in terms)
            args = [x for t in terms for x in (f"%{t}%", f"%{t}%")]
            rows = con.execute(f"SELECT a.*, 0 AS rank FROM answers a WHERE {like} LIMIT ?", (*args, limit * 3)).fetchall()
    out, seen = [], set()
    for r in rows:
        if kinds and r["kind"] not in kinds:
            continue
        key = (r["headline"] or "").strip().lower()
        if key in seen or not key:
            continue
        seen.add(key)
        out.append({
            "id": f"a-{r['id']}", "kind": r["kind"], "label": r["label"], "query": r["query"],
            "headline": r["headline"], "detail": json.loads(r["detail"] or "[]"), "confidence": r["confidence"],
            "sources": json.loads(r["sources"] or "[]"), "sow_impact": r["sow_impact"],
            "follow_up_question": r["follow_up"], "age_days": _age_days(r["checked_at"]),
        })
        if len(out) >= limit:
            break
    return out


def get_answer(answer_id: str) -> dict | None:
    m = re.fullmatch(r"a-(\d+)", answer_id or "")
    if not m:
        return None
    with connect() as con:
        r = con.execute("SELECT * FROM answers WHERE id=?", (int(m.group(1)),)).fetchone()
    if not r:
        return None
    return {"id": answer_id, "kind": r["kind"], "label": r["label"], "query": r["query"], "headline": r["headline"],
            "detail": json.loads(r["detail"] or "[]"), "confidence": r["confidence"],
            "sources": json.loads(r["sources"] or "[]"), "sow_impact": r["sow_impact"],
            "follow_up_question": r["follow_up"], "age_days": _age_days(r["checked_at"])}


# ------------------------------------------------------------------ queries for the MCP server
def list_engagements() -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT e.slug, e.client, e.project, e.industry, COUNT(s.id) AS calls, MAX(s.started_at) AS last_call "
            "FROM engagements e LEFT JOIN sessions s ON s.slug = e.slug GROUP BY e.slug ORDER BY last_call DESC")]


def get_engagement(name: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM engagements WHERE slug=? OR lower(client)=lower(?)", (name, name)).fetchone()
        if not row:
            row = con.execute("SELECT * FROM engagements WHERE lower(client) LIKE lower(?) OR slug LIKE ?",
                              (f"%{name}%", f"%{name}%")).fetchone()
        if not row:
            return None
        slug = row["slug"]
        ents = [dict(r) for r in con.execute(
            "SELECT en.name, en.type, ed.relation FROM edges ed JOIN entities en ON en.id = ed.entity_id WHERE ed.slug=?",
            (slug,))]
    data = previous_calls(slug)
    return {"engagement": dict(row), "entities": ents, **data}


def search(query: str, limit: int = 10) -> dict:
    terms = _terms(query)
    facts = []
    if terms:
        with connect() as con:
            like = " OR ".join("(f.value LIKE ? OR f.label LIKE ?)" for _ in terms)
            args = [x for t in terms for x in (f"%{t}%", f"%{t}%")]
            facts = [dict(r) for r in con.execute(
                f"SELECT e.client, e.project, f.label, f.value, f.evidence, f.updated_at FROM facts f "
                f"JOIN engagements e ON e.slug = f.slug WHERE {like} LIMIT ?", (*args, limit))]
            ents = [dict(r) for r in con.execute(
                "SELECT en.name, en.type, ed.relation, e.client, e.project FROM entities en "
                "JOIN edges ed ON ed.entity_id = en.id JOIN engagements e ON e.slug = ed.slug "
                "WHERE " + " OR ".join("lower(en.name) LIKE ?" for _ in terms) + " LIMIT ?",
                (*[f"%{t}%" for t in terms], limit))]
    else:
        ents = []
    return {"answers": known_answers(query, limit), "facts": facts, "entities": ents}
