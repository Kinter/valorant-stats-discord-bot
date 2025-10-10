import json
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Tuple

from .config import DB_FILE


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS links (
                user_id INTEGER PRIMARY KEY,
                name    TEXT NOT NULL,
                tag     TEXT NOT NULL,
                region  TEXT NOT NULL,
                ts      INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS aliases (
                alias       TEXT NOT NULL,
                alias_norm  TEXT NOT NULL UNIQUE,
                name        TEXT NOT NULL,
                tag         TEXT NOT NULL,
                region      TEXT NOT NULL,
                puuid       TEXT NOT NULL,
                ts          INTEGER NOT NULL,
                PRIMARY KEY(alias)
            );

            CREATE TABLE IF NOT EXISTS match_cache (
                match_id   TEXT NOT NULL,
                owner_key  TEXT NOT NULL,
                puuid      TEXT NOT NULL,
                map        TEXT,
                mode       TEXT,
                team       TEXT,
                result     TEXT,
                kills      INTEGER,
                deaths     INTEGER,
                assists    INTEGER,
                played_at  TEXT,
                raw_json   TEXT,
                ts         INTEGER NOT NULL,
                PRIMARY KEY (match_id, owner_key)
            );

            CREATE INDEX IF NOT EXISTS idx_match_cache_owner
            ON match_cache (owner_key, played_at DESC, ts DESC);
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


def _norm_alias(alias: str) -> str:
    return alias.strip().lower()


def upsert_alias(alias: str, name: str, tag: str, region: str, puuid: str) -> None:
    alias_norm = _norm_alias(alias)
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO aliases (alias, alias_norm, name, tag, region, puuid, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alias_norm) DO UPDATE SET
                alias=excluded.alias,
                name=excluded.name,
                tag=excluded.tag,
                region=excluded.region,
                puuid=excluded.puuid,
                ts=excluded.ts
            """,
            (alias, alias_norm, name, tag, region, puuid, now),
        )


def remove_alias(alias: str) -> bool:
    alias_norm = _norm_alias(alias)
    with _connect() as conn:
        cur = conn.execute("DELETE FROM aliases WHERE alias_norm = ?", (alias_norm,))
        return cur.rowcount > 0


def get_alias(alias: str) -> dict | None:
    alias_norm = _norm_alias(alias)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT alias, alias_norm, name, tag, region, puuid, ts
            FROM aliases
            WHERE alias_norm = ?
            """,
            (alias_norm,),
        ).fetchone()
    return _row_to_dict(row)


def list_aliases() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT alias, alias_norm, name, tag, region, puuid, ts FROM aliases ORDER BY alias COLLATE NOCASE"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def store_match_batch(owner_key: str, puuid: str, matches: Iterable[Dict[str, Any]]) -> int:
    now = int(time.time())
    rows: List[Tuple[Any, ...]] = []
    for match in matches:
        metadata = (match.get("metadata") or {}) if isinstance(match, dict) else {}
        match_id = (
            metadata.get("matchid")
            or metadata.get("matchId")
            or metadata.get("matchID")
            or match.get("match_id")
        )
        if not match_id:
            continue

        players = ((match.get("players") or {}).get("all_players") or []) if isinstance(match, dict) else []
        me = next((p for p in players if p.get("puuid") == puuid), None)
        stats = (me or {}).get("stats") or {}
        kills = stats.get("kills")
        deaths = stats.get("deaths")
        assists = stats.get("assists")

        team = me.get("team") if me else None
        result = None
        if team and isinstance(match.get("teams"), dict):
            team_data = match["teams"].get(team, {})
            has_won = team_data.get("has_won")
            if has_won is True:
                result = "win"
            elif has_won is False:
                result = "loss"

        played_at = metadata.get("game_start_patched") or metadata.get("game_start")
        map_name = metadata.get("map")
        mode_name = metadata.get("mode")

        raw_json = json.dumps(match, ensure_ascii=False)
        rows.append(
            (
                match_id,
                owner_key,
                puuid,
                map_name,
                mode_name,
                team,
                result,
                kills,
                deaths,
                assists,
                played_at,
                raw_json,
                now,
            )
        )

    if not rows:
        return 0

    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO match_cache (
                match_id, owner_key, puuid, map, mode, team, result,
                kills, deaths, assists, played_at, raw_json, ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, owner_key) DO UPDATE SET
                puuid=excluded.puuid,
                map=excluded.map,
                mode=excluded.mode,
                team=excluded.team,
                result=excluded.result,
                kills=excluded.kills,
                deaths=excluded.deaths,
                assists=excluded.assists,
                played_at=excluded.played_at,
                raw_json=excluded.raw_json,
                ts=excluded.ts
            """,
            rows,
        )
    return len(rows)


_ensure_schema()
