"""High-level API helpers for Riot-related lookups."""
from __future__ import annotations

from typing import Any, Dict, TypedDict

from .config import HENRIK_BASE
from .http import http_get
from .utils import is_account_not_found_error, q


class PlayerInfo(TypedDict, total=False):
    """Aggregated account/MMR information for a Riot player."""

    account: Dict[str, Any]
    mmr: Dict[str, Any]
    current_mmr: Dict[str, Any]
    puuid: str


async def fetch_player_info(name: str, tag: str, *, region: str) -> PlayerInfo:
    """Fetch Riot account, PUUID and MMR information for the given player.

    The helper consolidates HTTP requests and normalises error handling so that
    callers can rely on consistent exceptions (e.g. ``Account not found``).
    """

    name_q = q(name)
    tag_q = q(tag)

    try:
        account_resp = await http_get(f"{HENRIK_BASE}/v1/account/{name_q}/{tag_q}")
    except Exception as err:  # pragma: no cover - thin wrapper
        if is_account_not_found_error(err):
            raise RuntimeError("Account not found") from err
        raise

    account_data = account_resp.get("data") or {}
    puuid = account_data.get("puuid")
    if not puuid:
        raise RuntimeError("Account not found: missing PUUID")

    try:
        mmr_resp = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{name_q}/{tag_q}")
    except Exception as err:  # pragma: no cover - thin wrapper
        if is_account_not_found_error(err):
            raise RuntimeError("Account not found") from err
        raise

    mmr_data = mmr_resp.get("data") or {}
    current = mmr_data.get("current_data") or {}

    return {
        "account": account_data,
        "mmr": mmr_data,
        "current_mmr": current,
        "puuid": puuid,
    }
