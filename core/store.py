from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from typing import Any, Dict

from .config import DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    user_id INTEGER PRIMARY KEY,
    name    TEXT    NOT NULL,
    tag     TEXT    NOT NULL,
    region  TEXT    NOT NULL,
    ts      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_data (
    user_id    INTEGER PRIMARY KEY,
    payload    TEXT    NOT NULL,
    updated_at INTEGER NOT NULL
);
"""


def bootstrap_db() -> None:
    """Initialize the SQLite database and ensure the schema exists."""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> Dict[str, Any] | None:
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "tag": row["tag"],
        "region": row["region"],
        "ts": row["ts"],
    }


def upsert_link(user_id: int, name: str, tag: str, region: str) -> None:
    ts = int(time.time())
    with closing(_connect()) as conn:
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
            (user_id, name, tag, region, ts),
        )
        conn.commit()


def pop_link(user_id: int) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM links WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM links WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_data WHERE user_id = ?", (user_id,))
        conn.commit()
    return _row_to_dict(row)


def get_link(user_id: int) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM links WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_dict(row)


def list_links() -> list[Dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT * FROM links ORDER BY ts ASC").fetchall()
    return [item for row in rows if (item := _row_to_dict(row))]


def upsert_user_data(user_id: int, payload: Dict[str, Any], *, updated_at: int | None = None) -> None:
    ts = updated_at if updated_at is not None else int(time.time())
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with closing(_connect()) as conn:
        conn.execute(
            """
            INSERT INTO user_data (user_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload=excluded.payload,
                updated_at=excluded.updated_at
            """,
            (user_id, data, ts),
        )
        conn.commit()


def get_user_data(user_id: int) -> Dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT user_id, payload, updated_at FROM user_data WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "updated_at": row["updated_at"],
        "data": json.loads(row["payload"] or "{}"),
    }
