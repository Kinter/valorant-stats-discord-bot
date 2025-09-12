import json
import aiohttp
from typing import Optional, Dict, Any
from .config import HENRIK_API_KEY

_session: Optional[aiohttp.ClientSession] = None

async def ensure_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    return _session

async def http_get(url: str, *, params: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> dict:
    sess = await ensure_session()
    hdrs = dict(headers or {})
    if HENRIK_API_KEY:
        hdrs["Authorization"] = HENRIK_API_KEY
    async with sess.get(url, params=params, headers=hdrs) as r:
        text = await r.text()
        if r.status != 200:
            raise RuntimeError(f"GET {url} -> {r.status}: {text[:240]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON from {url}: {text[:120]}")

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
