import time
import urllib.parse
from typing import Optional

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
