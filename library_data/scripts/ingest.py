# scripts/ingest.py
import argparse, json, sqlite3, sys
from pathlib import Path
from typing import Iterable
from library_data.config import DB_PATH as DB_DEFAULT, ensure_dirs

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS books (
  id            TEXT PRIMARY KEY,
  entrydate     TEXT,
  title         TEXT,
  primaryauthor TEXT,
  language      TEXT,
  pages         INTEGER,
  genres        TEXT,
  subjects      TEXT,
  collections   TEXT,
  tags          TEXT,
  raw_json      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_books_entrydate     ON books(entrydate);
CREATE INDEX IF NOT EXISTS idx_books_title         ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_primaryauthor ON books(primaryauthor);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
  title,
  summary,
  tags,
  subjects,
  genres,
  author,
  content=''
);
"""

def ensure_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA_SQL)
    conn.commit()

def ensure_fts(conn: sqlite3.Connection):
    conn.executescript(FTS_SQL)
    conn.commit()

def _flatten_subjects(subj) -> list[str]:
    # subject can be { "0": [...], "2": [...], ... } or list; convert to flat unique strings
    out = []
    if isinstance(subj, dict):
        for v in subj.values():
            if isinstance(v, list):
                out += v
            elif isinstance(v, str):
                out.append(v)
    elif isinstance(subj, list):
        out = [x for x in subj if isinstance(x, str)]
    return sorted(set(s.strip() for s in out if s and isinstance(s, str)))

def _first(x):
    if isinstance(x, list) and x:
        return x[0]
    if isinstance(x, str):
        return x
    return None

def _int_or_none(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None

def _iter_author_dicts(authors):
    if isinstance(authors, dict):
        for v in authors.values():
            if isinstance(v, dict):
                yield v
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        yield x
    elif isinstance(authors, list):
        for a in authors:
            if isinstance(a, dict):
                yield a
            elif isinstance(a, list):
                for x in a:
                    if isinstance(x, dict):
                        yield x

def _author_name(rec: dict) -> str | None:
    pa = rec.get("primaryauthor")
    if isinstance(pa, str) and pa.strip():
        return pa
    for a in _iter_author_dicts(rec.get("authors")):
        for key in ("fl", "lf", "name"):
            val = a.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return None


def iter_records(json_path: Path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{json_path} is not an object keyed by books_id")
    for bid, rec in data.items():
        if not isinstance(rec, dict):
            continue
        yield bid, rec

def upsert_books(conn: sqlite3.Connection, items: Iterable[tuple[str, dict]], batch_size: int = 500):
    cur = conn.cursor()
    q = """
    INSERT INTO books (id, entrydate, title, primaryauthor, language, pages, genres, subjects, collections, tags, raw_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      entrydate=excluded.entrydate,
      title=excluded.title,
      primaryauthor=excluded.primaryauthor,
      language=excluded.language,
      pages=excluded.pages,
      genres=excluded.genres,
      subjects=excluded.subjects,
      collections=excluded.collections,
      tags=excluded.tags,
      raw_json=excluded.raw_json
    """
    buf = []
    n = 0
    for bid, rec in items:
        entrydate = rec.get("entrydate") or rec.get("date_entered")
        title = rec.get("title")
        primaryauthor = _author_name(rec)
        language = _first(rec.get("language")) or _first(rec.get("language_codeA"))
        pages = _int_or_none(rec.get("pages"))
        genres = ", ".join([g for g in (rec.get("genre") or []) if isinstance(g, str)])
        subjects = ", ".join(_flatten_subjects(rec.get("subject")))
        collections = ", ".join([c for c in (rec.get("collections") or []) if isinstance(c, str)])
        raw_tags = rec.get("tags")
        if isinstance(raw_tags, list):
            tags = ", ".join([t for t in raw_tags if isinstance(t, str)])
        elif isinstance(raw_tags, str):
            tags = raw_tags
        else:
            tags = ""
        raw_json = json.dumps(rec, ensure_ascii=False)

        buf.append((bid, entrydate, title, primaryauthor, language, pages, genres, subjects, collections, tags, raw_json))
        if len(buf) >= batch_size:
            cur.executemany(q, buf)
            conn.commit()
            n += len(buf)
            buf.clear()
    if buf:
        cur.executemany(q, buf)
        conn.commit()
        n += len(buf)
    return n

def rebuild_fts(conn: sqlite3.Connection):
    ensure_fts(conn)
    cur = conn.cursor()
    cur.execute("DELETE FROM books_fts")
    # pull minimal fields from raw_json to avoid schema drift
    rows = cur.execute("SELECT id, raw_json FROM books")
    batch = []
    for _id, raw in rows:
        rec = json.loads(raw)
        title = rec.get("title") or ""
        summary = rec.get("summary") or ""
        tags = ", ".join(rec.get("tags") or [])
        subjects = ", ".join(_flatten_subjects(rec.get("subject")))
        genres = ", ".join(rec.get("genre") or [])
        author = rec.get("primaryauthor") or ""
        batch.append((title, summary, tags, subjects, genres, author))
        if len(batch) >= 1000:
            cur.executemany("INSERT INTO books_fts (title, summary, tags, subjects, genres, author) VALUES (?,?,?,?,?,?)", batch)
            conn.commit()
            batch.clear()
    if batch:
        cur.executemany("INSERT INTO books_fts (title, summary, tags, subjects, genres, author) VALUES (?,?,?,?,?,?)", batch)
        conn.commit()

def main():
    ap = argparse.ArgumentParser(description="Ingest LibraryThing JSON exports into SQLite.")
    ap.add_argument("--db", default=str(DB_DEFAULT), help="Path to SQLite DB (default: data/db/catalog.db)")
    ap.add_argument("--file", action="append", required=True, help="Path to export JSON file (can repeat)")
    ap.add_argument("--rebuild-fts", action="store_true", help="Rebuild FTS5 index after ingest")
    ap.add_argument("--batch-size", type=int, default=500, help="Upsert batch size")
    args = ap.parse_args()

    db_path = Path(args.db)
    ensure_dirs()
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_db(conn)
        total = 0
        for f in args.file:
            p = Path(f)
            if not p.exists():
                print(f"skip (missing): {p}", file=sys.stderr)
                continue
            n = upsert_books(conn, iter_records(p), batch_size=args.batch_size)
            print(f"ingested {n} from {p}")
            total += n
        if args.rebuild_fts:
            print("rebuilding FTS…")
            rebuild_fts(conn)
        print(f"done. total upserts: {total} into {db_path}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
