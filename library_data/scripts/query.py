import argparse
import json
from typing import Optional
from pathlib import Path
from library_data.config import DB_PATH as DEFAULT_DB
from library_data.lib.lib_catalog import get_book, filter_books, search_text


def cmd_get(args):
    rec = get_book(args.db, args.id)
    if not rec:
        print("{}")
        return
    print(json.dumps(rec, ensure_ascii=False, indent=2))


def cmd_filter(args):
    rows = filter_books(
        args.db,
        tag=args.tag,
        genre=args.genre,
        collection=args.collection,
        date_added_after=args.date_added_after,
        limit=args.limit,
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_search(args):
    rows = search_text(args.db, args.query, args.limit)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def build_parser():
    ap = argparse.ArgumentParser(description="Query the catalog (get/filter/search).")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite DB")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_get = sub.add_parser("get", help="Get full record by id")
    ap_get.add_argument("id")
    ap_get.set_defaults(func=cmd_get)

    ap_filter = sub.add_parser("filter", help="Filter books by facets")
    ap_filter.add_argument("--tag")
    ap_filter.add_argument("--genre")
    ap_filter.add_argument("--collection")
    ap_filter.add_argument("--date-added-after")
    ap_filter.add_argument("--limit", type=int, default=50)
    ap_filter.set_defaults(func=cmd_filter)

    ap_search = sub.add_parser("search", help="Search title/fts")
    ap_search.add_argument("query")
    ap_search.add_argument("--limit", type=int, default=25)
    ap_search.set_defaults(func=cmd_search)

    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

