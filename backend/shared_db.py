from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR.parent / "patientpunk.db"
NORMALIZED_RECORDS_PATH = (
    BASE_DIR.parent / "6_11_hackathon" / "02_perpatient_records" / "records_normalized.csv"
)


def connect_sqlite(
    db_path: Path | str = DB_PATH,
    *,
    row_factory: sqlite3.Row | None = None,
) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    if row_factory is not None:
        connection.row_factory = row_factory
    return connection
