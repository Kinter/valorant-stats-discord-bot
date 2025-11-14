import time
import urllib.parse
from typing import Optional, Dict, Any

ALIAS_REGISTRATION_PROMPT = (
    "별명을 입력해 주세요. 먼저 `/별명등록` 명령으로 Riot ID를 등록할 수 있습니다."
)

REGIONS = {"ap","kr","eu","na","br","latam"}
_COOLDOWN_SEC = 5
_last_used: dict[int, float] = {}

def clean_text(value: Optional[str]) -> str:
    return (value or "").strip()

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
