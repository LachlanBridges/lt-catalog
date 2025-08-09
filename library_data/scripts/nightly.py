import os
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path

from library_data.config import DB_PATH, ensure_dirs
from library_data.scripts.export_lt import run_export
from library_data.scripts.settings import LT_TOKEN, UA
from library_data.scripts.ingest import ensure_db, iter_records, upsert_books, rebuild_fts
from library_data.scripts.enrich_levels import enrich


def _env_list(name: str) -> list[str] | None:
    v = os.getenv(name)
    if not v:
        return None
    return [x.strip() for x in v.split(',') if x.strip()]


def main():
    ensure_dirs()

    since_env = os.getenv('SINCE')
    if since_env:
        since = since_env
    else:
        since = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')

    collections = _env_list('COLLECTIONS')
    tags = _env_list('TAGS')
    search = os.getenv('SEARCH')

    out_path = run_export(fmt='json', since=since, collections=collections, tags=tags, search=search, headed=False)

    # Ingest exported JSON directly
    p = Path(out_path)
    con = sqlite3.connect(str(DB_PATH))
    try:
        ensure_db(con)
        n = upsert_books(con, iter_records(p))
        if os.getenv('REBUILD_FTS', 'false').lower() in ('1', 'true', 'yes'):
            rebuild_fts(con)
        print(f"nightly: ingested {n} from {p}")
    finally:
        con.close()

    # Enrich
    con = sqlite3.connect(str(DB_PATH))
    try:
        limit = int(os.getenv('ENRICH_LIMIT', '500'))
        sleep = float(os.getenv('ENRICH_SLEEP', '0.5'))
        scanned, wrote = enrich(con, lt_token=LT_TOKEN, limit=limit, sleep=sleep)
        print(f"nightly: enriched {wrote} (scanned {scanned})")
    finally:
        con.close()


if __name__ == '__main__':
    main()

