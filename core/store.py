import sqlite3
import time
from typing import Any, Dict

from .config import DB_FILE


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                user_id INTEGER PRIMARY KEY,
                name    TEXT NOT NULL,
                tag     TEXT NOT NULL,
                region  TEXT NOT NULL,
                ts      INTEGER NOT NULL
            )
            """
        )


def _row_to_dict(row: sqlite3.Row | None) -> Dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def upsert_link(user_id: int, name: str, tag: str, region: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO links (user_id, name, tag, region, ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name,
                tag=excluded.tag,
                region=excluded.region,
                ts=excluded.ts
            """,
            (user_id, name, tag, region, int(time.time())),
        )


def pop_link(user_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, name, tag, region, ts FROM links WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM links WHERE user_id = ?", (user_id,))
    return _row_to_dict(row)


def get_link(user_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, name, tag, region, ts FROM links WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_dict(row)


_ensure_schema()
