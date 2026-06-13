from __future__ import annotations

import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
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
