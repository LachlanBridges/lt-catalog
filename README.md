# LibraryThing Catalog Tools (library-data)

Tools to ingest LibraryThing exports into SQLite, enrich with reading-level metadata from OpenLibrary, and automate browser exports via Playwright.

## Features
- Ingest LibraryThing JSON export to SQLite (`books` table) with optional FTS5 index.
- Enrich reading levels by probing OpenLibrary (Lexile, grades, ages) with best-effort LT ISBN clustering.
- Automate LibraryThing export (JSON or MARC) with a stored Playwright session.
- Importable package (`library_data`) with CLI entrypoints.

## Status / TODO
- Vector search (`search_semantic`) is a placeholder; plan is to build embeddings and FAISS/Chroma, then map vector IDs to `books.id`.
- Playwright export expects a saved session at `library-data/secrets/.state.json`.
- Minimal validation/tests. Consider adding unit tests for parsing and DB upsert paths.

## Project Layout
- `library_data/` – Python package (importable)
  - `lib/` – pure libraries (`lib_catalog.py`, `isbn_utils.py`)
  - `scripts/` – CLI modules (`ingest.py`, `enrich_levels.py`, `export_lt.py`, `capture_playwright_state.py`, `settings.py`)
  - `config.py` – central config for data dirs and DB path
- `library-data/` – runtime data (configurable via `LIBRARY_DATA_DIR`)
  - `data/db/` – SQLite DBs
  - `exports/` – exported files downloaded by Playwright
  - `secrets/` – session state (`.state.json`) and browser profile
  - `.env` – optional env overrides for runtime

## Requirements
- Python 3.10+
- For export automation: Playwright + Chromium (installed automatically in Docker; locally run `playwright install` if needed)

## Installation
- Local (editable install):
  - `pip install -e .`
  - Copy `.env.example` to `.env` (or put env in `library-data/.env`):
    - `LIBRARY_DATA_DIR=./library-data`
    - `LT_TOKEN=...` (optional)
    - `UA=library-data/levels (+mailto:you@example.com)`

- Docker:
  - `docker build -t library-data .`
  - Create the data directory on the host: `mkdir -p library-data/{data/db,exports,secrets}`

## Usage
- Ingest (local):
  - `python -m library_data.scripts.ingest --file library-data/exports/lt-export_full.json`
- Enrich (local):
  - `python -m library_data.scripts.enrich_levels --limit 200`
- Export (local; needs saved state):
  - First capture state: `python -m library_data.scripts.capture_playwright_state`
  - Then export: `python -m library_data.scripts.export_lt --since 2024-01-01 --fmt json`

- With console scripts (after `pip install -e .`):
  - `library-data-ingest --file library-data/exports/lt-export_full.json`
  - `library-data-enrich-levels --limit 200`
  - `library-data-capture-state`
  - `library-data-export-lt --since 2024-01-01 --fmt json`

- Docker (mount host data dir):
  - Ingest:
    - `docker run --rm -it -v "$PWD/library-data:/app/library-data" -e LIBRARY_DATA_DIR=/app/library-data library-data library-data-ingest --file /app/library-data/exports/lt-export_full.json`
  - Enrich:
    - `docker run --rm -it -v "$PWD/library-data:/app/library-data" -e LIBRARY_DATA_DIR=/app/library-data -e LT_TOKEN=... library-data library-data-enrich-levels --limit 200`
  - Export (needs `/app/library-data/secrets/.state.json` inside the container volume):
    - `docker run --rm -it -v "$PWD/library-data:/app/library-data" -e LIBRARY_DATA_DIR=/app/library-data library-data library-data-export-lt --since 2024-01-01 --fmt json`

## Scheduling (Cron)
You have two good options:

1) Host cron (recommended for simplicity)
- Add a crontab entry that runs the container on a schedule:
```
# Nightly ingest and enrich at 02:00
0 2 * * * docker run --rm -v /srv/library-data:/app/library-data -e LIBRARY_DATA_DIR=/app/library-data -e LT_TOKEN=... library-data library-data-ingest --file /app/library-data/exports/lt-export_full.json >> /var/log/library-data.log 2>&1
10 2 * * * docker run --rm -v /srv/library-data:/app/library-data -e LIBRARY_DATA_DIR=/app/library-data -e LT_TOKEN=... library-data library-data-enrich-levels --limit 500 >> /var/log/library-data.log 2>&1
```

2) Cron inside a container (self-contained image)
- Build a derived image that installs and runs `cron`:
```
FROM library-data as cron
RUN apt-get update && apt-get install -y --no-install-recommends cron && rm -rf /var/lib/apt/lists/*
# Example crontab: run ingest at 02:00 daily
RUN echo "0 2 * * * library-data-ingest --file /app/library-data/exports/lt-export_full.json >> /var/log/cron.log 2>&1" > /etc/cron.d/library-data \
 && chmod 0644 /etc/cron.d/library-data \
 && crontab /etc/cron.d/library-data
CMD ["cron", "-f"]
```
- Run with your data volume mounted: `-v /srv/library-data:/app/library-data`.

Host cron is generally easier to operate and observe; container-internal cron is useful when you deploy to systems without a host scheduler.

## Development
- Makefile helpers:
  - `make install` – install package locally
  - `make ingest FILE=exports/lt-export_full.json`
  - `make enrich LIMIT=200`
  - `make docker-build`
  - `make docker-enrich LIMIT=200`

## Notes
- SQLite FTS5 is optional; enable with `--rebuild-fts` on ingest.
- OpenLibrary requests include a polite UA; set `UA` to your contact.
- LibraryThing ISBN clustering uses `LT_TOKEN` if provided; otherwise enrichment uses only OpenLibrary heuristics.

