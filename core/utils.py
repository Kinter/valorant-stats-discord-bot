import time
import urllib.parse
from typing import Any, Dict, Mapping, Optional

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
