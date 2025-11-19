import time
import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional

ALIAS_REGISTRATION_PROMPT = (
    "별명을 입력해 주세요. 먼저 `/별명등록` 명령으로 Riot ID를 등록할 수 있습니다."
)

REGIONS = {"ap","kr","eu","na","br","latam"}
_COOLDOWN_SEC = 5
_last_used: dict[int, float] = {}

def clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _metadata_candidate(value: Any) -> Optional[str]:
    if isinstance(value, str):
        value = value.strip()
        return value or None

    if isinstance(value, Mapping):
        preferred_keys = (
            "patched",
            "name",
            "display_name",
            "displayName",
            "label",
        )
        for key in preferred_keys:
            if key in value:
                candidate = _metadata_candidate(value.get(key))
                if candidate:
                    return candidate

        localization_keys = ("localized", "localizations", "translations")
        for key in localization_keys:
            localized = value.get(key)
            if isinstance(localized, Mapping):
                for locale_key in ("ko-KR", "ko", "en-US", "en"):
                    candidate = _metadata_candidate(localized.get(locale_key))
                    if candidate:
                        return candidate

        for nested in value.values():
            candidate = _metadata_candidate(nested)
            if candidate:
                return candidate

    return None


def metadata_label(
    metadata: Mapping[str, Any] | None,
    key: str,
    *,
    default: str = "?",
) -> str:
    if not isinstance(metadata, Mapping):
        return default

    raw_value = metadata.get(key)
    candidate = _metadata_candidate(raw_value)

    if not candidate:
        alt_keys = ()
        if key == "map":
            alt_keys = ("map_name", "mapid", "mapId", "mapID")
        elif key == "mode":
            alt_keys = ("queue", "mode_name", "modeid", "modeId", "modeID")

        for alt_key in alt_keys:
            candidate = _metadata_candidate(metadata.get(alt_key))
            if candidate:
                break

    return candidate or default


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _coerce_boolish(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized in {"win", "won", "victory", "true", "t", "1", "yes", "y"}:
            return True
        if normalized in {"loss", "lost", "defeat", "false", "f", "0", "no", "n"}:
            return False
    return None


def team_outcome_from_entry(entry: Mapping[str, Any] | None) -> Optional[bool]:
    if not isinstance(entry, Mapping):
        return None

    result = _coerce_boolish(entry.get("has_won"))
    if result is None:
        result = _coerce_boolish(entry.get("won"))

    if result is None:
        rounds_won = _as_int(entry.get("rounds_won"))
        rounds_lost = _as_int(entry.get("rounds_lost"))
        if rounds_won is not None and rounds_lost is not None:
            if rounds_won > rounds_lost:
                result = True
            elif rounds_lost > rounds_won:
                result = False

    return result


def _register_team_entry(
    registry: Dict[str, Mapping[str, Any]], key: Any, entry: Mapping[str, Any]
) -> None:
    if key is None:
        return

    key_str = str(key)
    if not key_str:
        return

    base = clean_text(key_str)
    if not base:
        return

    variants = {key_str, base, base.lower(), base.upper(), base.capitalize()}
    for variant in variants:
        if variant:
            registry[variant] = entry


def team_result(teams: Mapping[str, Any] | None, team_name: Optional[str]) -> Optional[bool]:
    if not team_name:
        return None

    team_clean = clean_text(team_name)
    if not team_clean:
        return None

    entries: Dict[str, Mapping[str, Any]] = {}

    if isinstance(teams, Mapping):
        for key, value in teams.items():
            if isinstance(value, Mapping):
                _register_team_entry(entries, key, value)
    elif isinstance(teams, Sequence) and not isinstance(teams, (str, bytes, bytearray)):
        for value in teams:
            if not isinstance(value, Mapping):
                continue
            key_candidates = (
                value.get("team"),
                value.get("team_name"),
                value.get("name"),
                value.get("id"),
                value.get("team_id"),
                value.get("side"),
            )
            for candidate in key_candidates:
                if candidate:
                    _register_team_entry(entries, candidate, value)
                    break
    else:
        return None

    if not entries:
        return None

    candidates = (
        team_name,
        team_clean,
        team_clean.lower(),
        team_clean.upper(),
        team_clean.capitalize(),
    )

    for key in candidates:
        if not key:
            continue
        entry = entries.get(key)
        if not entry:
            continue
        result = team_outcome_from_entry(entry)
        if result is not None:
            return result

    target = team_clean.lower()
    for key, value in entries.items():
        if clean_text(str(key)).lower() == target:
            result = team_outcome_from_entry(value)
            if result is not None:
                return result

    return None

def norm_region(s: str) -> str:
    s = clean_text(s).lower()
    return s if s in REGIONS else "ap"

def check_cooldown(user_id: int) -> Optional[int]:
    now = time.time()
    last = _last_used.get(user_id, 0)
    remain = _COOLDOWN_SEC - int(now - last)
    if remain > 0:
        return remain
    _last_used[user_id] = now
    return None

def q(s: str) -> str:
    return urllib.parse.quote(clean_text(s), safe="")

def tier_key(name: str) -> str:
    return (clean_text(name) or "Unrated").lower().replace(" ", "")

def trunc2(x: float) -> float:
    return int(x * 100) / 100

def alias_display(info: Dict[str, Any]) -> str:
    alias = clean_text(info.get("alias", ""))
    name = clean_text(info.get("name", ""))
    tag = clean_text(info.get("tag", ""))
    label = f"{alias} ({name}#{tag})" if alias else f"{name}#{tag}"
    return label if len(label) <= 100 else (label[:97] + "...")


def is_account_not_found_error(error: Exception) -> bool:
    message = str(error) if error else ""
    return "Account not found" in message


def format_exception_message(error: Exception) -> str:
    if error is None:
        return "Unknown error"
    message = str(error).strip()
    return message if message else error.__class__.__name__
