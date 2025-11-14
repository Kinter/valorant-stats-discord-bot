import json
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Tuple, Optional

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

            CREATE TABLE IF NOT EXISTS daily_summary (
                summary_date TEXT NOT NULL,
                owner_key    TEXT NOT NULL,
                alias_norm   TEXT NOT NULL,
                puuid        TEXT NOT NULL,
                matches      INTEGER NOT NULL,
                wins         INTEGER NOT NULL,
                losses       INTEGER NOT NULL,
                rr_delta     INTEGER NOT NULL,
                kills        INTEGER NOT NULL,
                deaths       INTEGER NOT NULL,
                assists      INTEGER NOT NULL,
                ts           INTEGER NOT NULL,
                PRIMARY KEY (summary_date, owner_key)
            );

            CREATE INDEX IF NOT EXISTS idx_daily_summary_alias
            ON daily_summary (summary_date, alias_norm);

            CREATE TABLE IF NOT EXISTS act_summary (
                act_id    TEXT NOT NULL,
                owner_key TEXT NOT NULL,
                alias_norm TEXT NOT NULL,
                puuid      TEXT NOT NULL,
                matches    INTEGER NOT NULL,
                wins       INTEGER NOT NULL,
                losses     INTEGER NOT NULL,
                rr_delta   INTEGER NOT NULL,
                kills      INTEGER NOT NULL,
                deaths     INTEGER NOT NULL,
                assists    INTEGER NOT NULL,
                ts         INTEGER NOT NULL,
                PRIMARY KEY (act_id, owner_key)
            );

            CREATE INDEX IF NOT EXISTS idx_act_summary_alias
            ON act_summary (act_id, alias_norm);

            CREATE TABLE IF NOT EXISTS alert_channels (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                ts         INTEGER NOT NULL
            );
            """
        )


def _row_to_dict(row: sqlite3.Row | None) -> Dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


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


def search_aliases(query: str | None = None, limit: int = 25) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    limit = max(1, min(25, limit or 25))
    with _connect() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute(
                """
                SELECT alias, alias_norm, name, tag, region, puuid, ts
                FROM aliases
                WHERE alias_norm LIKE ?
                   OR LOWER(name) LIKE ?
                   OR LOWER(tag) LIKE ?
                ORDER BY alias COLLATE NOCASE
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT alias, alias_norm, name, tag, region, puuid, ts
                FROM aliases
                ORDER BY alias COLLATE NOCASE
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def store_match_batch(owner_key: str, puuid: str, matches: Iterable[Dict[str, Any]]) -> int:
    now = int(time.time())
    rows: List[Tuple[Any, ...]] = []
    match_ids: List[str] = []
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
        match_ids.append(match_id)

    if not rows:
        return 0

    unique_match_ids = list(dict.fromkeys(match_ids))

    with _connect() as conn:
        existing_ids: set[str] = set()
        if unique_match_ids:
            chunk_size = 500
            for i in range(0, len(unique_match_ids), chunk_size):
                chunk = unique_match_ids[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                query = (
                    f"SELECT match_id FROM match_cache "
                    f"WHERE owner_key = ? AND match_id IN ({placeholders})"
                )
                params: List[Any] = [owner_key, *chunk]
                rows_existing = conn.execute(query, params).fetchall()
                existing_ids.update(row["match_id"] for row in rows_existing)

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
    new_rows = [mid for mid in unique_match_ids if mid not in existing_ids]
    return len(new_rows)


def latest_match(owner_key: str) -> Dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT match_id, owner_key, puuid, map, mode, team, result, kills, deaths,
                   assists, played_at, raw_json, ts
            FROM match_cache
            WHERE owner_key = ?
            ORDER BY played_at DESC, ts DESC
            LIMIT 1
            """,
            (owner_key,),
        ).fetchone()
    return _row_to_dict(row)


def upsert_daily_summary(
    summary_date: str,
    owner_key: str,
    alias_norm: str,
    puuid: str,
    *,
    matches: int,
    wins: int,
    losses: int,
    rr_delta: int,
    kills: int,
    deaths: int,
    assists: int,
) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_summary (
                summary_date, owner_key, alias_norm, puuid,
                matches, wins, losses, rr_delta, kills, deaths, assists, ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(summary_date, owner_key) DO UPDATE SET
                matches=excluded.matches,
                wins=excluded.wins,
                losses=excluded.losses,
                rr_delta=excluded.rr_delta,
                kills=excluded.kills,
                deaths=excluded.deaths,
                assists=excluded.assists,
                ts=excluded.ts
            """,
            (
                summary_date,
                owner_key,
                alias_norm,
                puuid,
                matches,
                wins,
                losses,
                rr_delta,
                kills,
                deaths,
                assists,
                now,
            ),
        )


def fetch_daily_summary(summary_date: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT summary_date, owner_key, alias_norm, puuid,
                   matches, wins, losses, rr_delta, kills, deaths, assists, ts
            FROM daily_summary
            WHERE summary_date = ?
            ORDER BY wins DESC, matches DESC, alias_norm ASC
            """,
            (summary_date,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert_act_summary(
    act_id: str,
    owner_key: str,
    alias_norm: str,
    puuid: str,
    *,
    matches: int,
    wins: int,
    losses: int,
    rr_delta: int,
    kills: int,
    deaths: int,
    assists: int,
) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO act_summary (
                act_id, owner_key, alias_norm, puuid,
                matches, wins, losses, rr_delta, kills, deaths, assists, ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(act_id, owner_key) DO UPDATE SET
                matches=excluded.matches,
                wins=excluded.wins,
                losses=excluded.losses,
                rr_delta=excluded.rr_delta,
                kills=excluded.kills,
                deaths=excluded.deaths,
                assists=excluded.assists,
                ts=excluded.ts
            """,
            (
                act_id,
                owner_key,
                alias_norm,
                puuid,
                matches,
                wins,
                losses,
                rr_delta,
                kills,
                deaths,
                assists,
                now,
            ),
        )


def fetch_act_summary(act_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT act_id, owner_key, alias_norm, puuid,
                   matches, wins, losses, rr_delta, kills, deaths, assists, ts
            FROM act_summary
            WHERE act_id = ?
            ORDER BY rr_delta DESC, wins DESC, alias_norm ASC
            """,
            (act_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_alert_channel(guild_id: int, channel_id: int) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO alert_channels (guild_id, channel_id, ts)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                ts=excluded.ts
            """,
            (guild_id, channel_id, now),
        )


def remove_alert_channel(guild_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM alert_channels WHERE guild_id = ?", (guild_id,))


def get_alert_channel(guild_id: int) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT channel_id FROM alert_channels WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return row[0] if row else None


def list_alert_channels() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT guild_id, channel_id, ts FROM alert_channels ORDER BY guild_id"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


_ensure_schema()
