# scripts/lib_catalog.py
import json, sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterable
from library_data.config import DB_PATH as DB_DEFAULT

def _conn(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con

def get_book(db_path: str | Path = DB_DEFAULT, book_id: str = "") -> Optional[Dict[str, Any]]:
    with _conn(db_path) as con:
        r = con.execute("SELECT raw_json FROM books WHERE id = ?", (book_id,)).fetchone()
        if not r:
            return None
        return json.loads(r["raw_json"])

def _like_clause(field: str) -> str:
    # basic LIKE match for comma-joined fields
    return f"LOWER({field}) LIKE ?"

def filter_books(
    db_path: str | Path = DB_DEFAULT,
    *,
    tag: Optional[str] = None,
    genre: Optional[str] = None,
    collection: Optional[str] = None,
    date_added_after: Optional[str] = None,  # YYYY-MM-DD
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Returns lightweight rows for display/ranking; fetch full via get_book().
    """
    q = ["SELECT id, title, primaryauthor, entrydate, genres, subjects, collections FROM books WHERE 1=1"]
    args: list[Any] = []

    if tag:
        q.append(f"AND {_like_clause('tags')}")
        args.append(f"%{tag.lower()}%")
    if genre:
        q.append(f"AND {_like_clause('genres')}")
        args.append(f"%{genre.lower()}%")
    if collection:
        q.append(f"AND {_like_clause('collections')}")
        args.append(f"%{collection.lower()}%")
    if date_added_after:
        q.append("AND entrydate >= ?")
        args.append(date_added_after)

    q.append("ORDER BY entrydate DESC, title COLLATE NOCASE ASC")
    q.append("LIMIT ?")
    args.append(limit)

    with _conn(db_path) as con:
        rows = con.execute(" ".join(q), args).fetchall()
        return [dict(r) for r in rows]

def search_text(
    db_path: str | Path = DB_DEFAULT,
    query: str = "",
    limit: int = 25
) -> List[Dict[str, Any]]:
    """
    FTS5 if available; else fallback to title LIKE.
    """
    with _conn(db_path) as con:
        # FTS5 path
        has_fts = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='books_fts'"
        ).fetchone() is not None

        if has_fts:
            q = """
            SELECT b.id, b.title, b.primaryauthor, b.entrydate,
                   bm25(books_fts, 1.0, 0.8, 0.3, 0.5, 0.5, 0.8) AS score
            FROM books_fts
            JOIN books b ON b.rowid = books_fts.rowid
            WHERE books_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """
            rows = con.execute(q, (query, limit)).fetchall()
            return [dict(r) for r in rows]

        # fallback LIKE
        rows = con.execute(
            "SELECT id, title, primaryauthor, entrydate FROM books WHERE LOWER(title) LIKE ? ORDER BY title LIMIT ?",
            (f"%{query.lower()}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

def search_semantic(
    index_dir: str | Path,
    query: str,
    k: int = 10,
    *,
    db_path: str | Path = DB_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Placeholder; wire FAISS/Chroma later.
    Return shape mirrors search_text().
    """
    raise NotImplementedError("Vector search not wired yet. Build embeddings + FAISS, then map vector_ids -> books.id.")

def upsert_from_json(
    db_path: str | Path,
    json_obj: Dict[str, Any] | Iterable[tuple[str, Dict[str, Any]]]
) -> int:
    """
    Convenience: upsert from an in-memory JSON export.
    """
    import tempfile
from library_data.scripts.ingest import upsert_books  # reuse logic

    if isinstance(json_obj, dict):
        items = json_obj.items()
    else:
        items = json_obj

    with _conn(db_path) as con:
        # ensure schema
        from library_data.scripts.ingest import ensure_db  # lazy to avoid circulars
        ensure_db(con)
        return upsert_books(con, items)
