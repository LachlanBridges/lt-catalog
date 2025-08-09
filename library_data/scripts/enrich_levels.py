from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
import sqlite3, requests
from library_data.lib.isbn_utils import explode_isbns_with_lt, probe_openlibrary_isbns, expand_via_openlibrary
from library_data.scripts import settings
from library_data.config import DB_PATH as DB_DEFAULT, ensure_dirs

UA = settings.UA


DB_DEFAULT = DB_DEFAULT

RE_LEXILE_ANY   = re.compile(r"\b(\d{3,4})\s*[lL]\b")
RE_LEXILE_RANGE = re.compile(r"\blexile[^0-9]*?(\d{3,4})\s*[-–]\s*(\d{3,4})\b", re.I)
RE_GRADES_RANGE = re.compile(r"\bgrades?\s*(\d+)\s*[-–]\s*(\d+)\b", re.I)
RE_GRADE_SINGLE = re.compile(r"\bgrade\s*(?:level\s*)?(\d+)\b", re.I)
RE_AGES_RANGE   = re.compile(r"\bages?\s*(\d+)\s*[-–]\s*(\d+)\b", re.I)
RE_AGE_SINGLE   = re.compile(r"\bage\s*(\d+)\b", re.I)

def digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit() or ch.upper() == "X")

def isbn10_to13(isbn10: str) -> str | None:
    core = digits(isbn10).upper()
    if len(core) != 10:
        return None
    base = "978" + core[:9]
    total = sum((int(d) if i % 2 == 0 else int(d) * 3) for i, d in enumerate(base))
    check = (10 - (total % 10)) % 10
    return base + str(check)

def collect_isbns13(rec) -> list[str]:
    cand = []
    isbn_obj = rec.get("isbn")
    if isinstance(isbn_obj, dict):
        cand += [v for v in isbn_obj.values() if isinstance(v, str)]
    elif isinstance(isbn_obj, list):
        cand += [v for v in isbn_obj if isinstance(v, str)]
    elif isinstance(isbn_obj, str):
        cand.append(isbn_obj)
    for k in ("originalisbn", "asin", "ean", "upc"):
        v = rec.get(k)
        if isinstance(v, str):
            cand.append(v)
        elif isinstance(v, list):
            cand += [x for x in v if isinstance(x, str)]
    # normalize -> 13
    norm = []
    for v in cand:
        d = digits(v)
        if len(d) == 13:
            norm.append(d)
        elif len(d) == 10:
            c13 = isbn10_to13(d)
            if c13:
                norm.append(c13)
    seen, out = set(), []
    for x in norm:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def ensure_table(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS book_levels (
      book_id    TEXT PRIMARY KEY,
      lexile_min INTEGER,
      lexile_max INTEGER,
      grade_min  INTEGER,
      grade_max  INTEGER,
      age_min    INTEGER,
      age_max    INTEGER,
      source     TEXT,
      raw_json   TEXT,
      updated_at TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()

def _extract_from_text(blob: str, out: dict):
    if not blob or not isinstance(blob, str):
        return
    m = RE_LEXILE_RANGE.search(blob)
    if m:
        out.setdefault("lexile_min", int(m.group(1)))
        out.setdefault("lexile_max", int(m.group(2)))
    if "lexile_min" not in out or "lexile_max" not in out:
        m2 = RE_LEXILE_ANY.search(blob)
        if m2:
            n = int(m2.group(1))
            out.setdefault("lexile_min", n)
            out.setdefault("lexile_max", n)
    mg = RE_GRADES_RANGE.search(blob)
    if mg:
        out.setdefault("grade_min", int(mg.group(1)))
        out.setdefault("grade_max", int(mg.group(2)))
    else:
        mg2 = RE_GRADE_SINGLE.search(blob)
        if mg2:
            g = int(mg2.group(1))
            out.setdefault("grade_min", g)
            out.setdefault("grade_max", g)
    ma = RE_AGES_RANGE.search(blob)
    if ma:
        out.setdefault("age_min", int(ma.group(1)))
        out.setdefault("age_max", int(ma.group(2)))
    else:
        ma2 = RE_AGE_SINGLE.search(blob)
        if ma2:
            a = int(ma2.group(1))
            out.setdefault("age_min", a)
            out.setdefault("age_max", a)

def parse_levels_rich(obj: dict | None) -> dict:
    out = {}
    if not obj:
        return out
    subs = obj.get("subjects") or []
    for s in subs:
        if isinstance(s, str):
            _extract_from_text(s, out)
    desc = obj.get("description")
    if isinstance(desc, dict):
        _extract_from_text(desc.get("value"), out)
    elif isinstance(desc, str):
        _extract_from_text(desc, out)
    notes = obj.get("notes")
    if isinstance(notes, dict):
        _extract_from_text(notes.get("value"), out)
    elif isinstance(notes, str):
        _extract_from_text(notes, out)
    return out

def lt_subjects_fallback(rec: dict) -> dict:
    subj = rec.get("subject")
    flat = []
    if isinstance(subj, dict):
        for v in subj.values():
            if isinstance(v, list):
                flat += [x for x in v if isinstance(x, str)]
            elif isinstance(v, str):
                flat.append(v)
    elif isinstance(subj, list):
        flat = [x for x in subj if isinstance(x, str)]
    blob = " ; ".join(flat).lower()
    out = {}
    if any(tok in blob for tok in ("juvenile", "children", "young adult")):
        out["age_min"] = 5
        out["age_max"] = 12
    return out

def fetch_ol_pair(session: requests.Session, isbn13: str):
    ed = wk = None
    r = session.get(f"https://openlibrary.org/isbn/{isbn13}.json", timeout=15)
    if not r.ok:
        return None, None
    ed = r.json()
    if ed.get("works"):
        wkkey = ed["works"][0].get("key")
        if wkkey:
            r2 = session.get(f"https://openlibrary.org{wkkey}.json", timeout=15)
            if r2.ok:
                wk = r2.json()
    return ed, wk

def enrich(conn, *, lt_token: str | None, limit=500, sleep=0.5, probe_all=False):
    conn.row_factory = sqlite3.Row
    ensure_table(conn)

    rows = conn.execute("""
      SELECT id, raw_json FROM books
      WHERE id NOT IN (SELECT book_id FROM book_levels)
    """).fetchall()

    s = requests.Session()
    s.headers["User-Agent"] = UA

    scanned = wrote = 0
    for row in rows[:limit]:
        scanned += 1
        bid = row["id"]
        rec = json.loads(row["raw_json"])

        base_isbns = collect_isbns13(rec)
        # expand via LT cluster if token provided
        cluster = explode_isbns_with_lt(lt_token, base_isbns) if base_isbns else []
        expanded = cluster or base_isbns  # fall back to base if cluster empty

        # ensure the ISBN actually exists on OL
        candidates = probe_openlibrary_isbns(expanded) if expanded else []
        if not candidates and not probe_all:
            # still try with base list (cheap)
            candidates = base_isbns

        data = {}
        ed = wk = None
        for isbn in candidates:
            try:
                ed, wk = fetch_ol_pair(s, isbn)
            except requests.RequestException:
                continue
            for obj in (ed, wk):
                d = parse_levels_rich(obj)
                for k, v in d.items():
                    if v is not None and k not in data:
                        data[k] = v
            if data:
                break

        if not data:
            data = lt_subjects_fallback(rec)

        if data:
            conn.execute("""
              INSERT INTO book_levels (book_id, lexile_min, lexile_max, grade_min, grade_max, age_min, age_max, source, raw_json)
              VALUES (?,?,?,?,?,?,?,?,?)
              ON CONFLICT(book_id) DO UPDATE SET
                lexile_min=COALESCE(excluded.lexile_min, lexile_min),
                lexile_max=COALESCE(excluded.lexile_max, lexile_max),
                grade_min=COALESCE(excluded.grade_min, grade_min),
                grade_max=COALESCE(excluded.grade_max, grade_max),
                age_min=COALESCE(excluded.age_min, age_min),
                age_max=COALESCE(excluded.age_max, age_max),
                source='openlibrary+ltcluster',
                raw_json=excluded.raw_json,
                updated_at=datetime('now')
            """, (bid,
                  data.get("lexile_min"), data.get("lexile_max"),
                  data.get("grade_min"), data.get("grade_max"),
                  data.get("age_min"), data.get("age_max"),
                  "openlibrary+ltcluster",
                  json.dumps({"base_isbns": base_isbns, "expanded": expanded, "picked": candidates[:3], "ed": ed, "wk": wk}, ensure_ascii=False)))
            conn.commit(); wrote += 1

        time.sleep(sleep)

    return scanned, wrote

def main():
    ap = argparse.ArgumentParser(description="Enrich catalog with reading levels: LT thingISBN expansion + OpenLibrary probe.")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    ap.add_argument("--lt-token", default=settings.LT_TOKEN, help="LibraryThing API token for thingISBN (optional but recommended)")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    ensure_dirs()
    con = sqlite3.connect(str(args.db))
    try:
        scanned, wrote = enrich(con, lt_token=args.lt_token, limit=args.limit, sleep=args.sleep)
        print(f"scanned {scanned} books, wrote {wrote} level rows")
    finally:
        con.close()

if __name__ == "__main__":
    main()
