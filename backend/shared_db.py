from __future__ import annotations

import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a repo-root .env into the environment (stdlib only).

    Runs before any env is read so a plain `uvicorn backend.search_api.app:app` picks up
    keys without python-dotenv or --env-file. Real environment values always win.
    """
    env_path = BASE_DIR.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

# Configurable so the API can point at a local / controlled copy rather than the in-repo DB.
DB_PATH = Path(os.environ.get("PATIENTPUNK_DB", str(BASE_DIR.parent / "patientpunk.db")))


def connect_sqlite(
    db_path: Path | str = DB_PATH,
    *,
    row_factory: sqlite3.Row | None = None,
) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    if row_factory is not None:
        connection.row_factory = row_factory
    return connection
