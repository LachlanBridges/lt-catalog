import os
from pathlib import Path


def _default_data_root() -> Path:
    # Prefer env var, else ./library-data under current working directory
    env = os.getenv("LIBRARY_DATA_DIR")
    return Path(env).resolve() if env else (Path.cwd() / "library-data").resolve()


# Base directories for runtime data (db, exports, secrets)
DATA_ROOT = _default_data_root()
DB_DIR = DATA_ROOT / "data" / "db"
DB_PATH = DB_DIR / "catalog.db"
EXPORTS_DIR = DATA_ROOT / "exports"
SECRETS_DIR = DATA_ROOT / "secrets"


def ensure_dirs():
    for p in (DB_DIR, EXPORTS_DIR, SECRETS_DIR):
        p.mkdir(parents=True, exist_ok=True)

