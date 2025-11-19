import asyncio
import json
import logging
from typing import Optional, Dict, Any

import aiohttp

from .config import HENRIK_API_KEY, HTTP_TIMEOUT

logger = logging.getLogger(__name__)

_session: Optional[aiohttp.ClientSession] = None


async def ensure_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        logger.debug("Creating new aiohttp ClientSession")
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        )
    return _session


def _extract_error_detail(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:240]

    if isinstance(data, dict):
        for key in ("detail", "message", "error", "errors"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                return json.dumps(value)[:240]
            if isinstance(value, list):
                return json.dumps(value)[:240]
    return text[:240]


async def http_get(
    url: str,
    *,
    params: Dict[str, Any] | None = None,
    headers: Dict[str, str] | None = None,
) -> dict:
    sess = await ensure_session()
    hdrs = dict(headers or {})
    if HENRIK_API_KEY:
        hdrs["Authorization"] = HENRIK_API_KEY

    logger.info("HTTP GET %s params=%s", url, params)
    try:
        async with sess.get(url, params=params, headers=hdrs) as response:
            text = await response.text()
            if response.status != 200:
                detail = _extract_error_detail(text)
                logger.error(
                    "HTTP GET failed %s -> %s %s | detail=%s",
                    url,
                    response.status,
                    response.reason,
                    detail,
                )
                raise RuntimeError(
                    f"GET {url} -> {response.status} {response.reason}: {detail}"
                )

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                logger.error("Invalid JSON from %s: %s", url, text[:240])
                raise RuntimeError(f"Invalid JSON from {url}: {text[:120]}")

            logger.debug("HTTP GET success %s (%s bytes)", url, len(text))
            return payload
    except asyncio.TimeoutError as exc:
        logger.error("HTTP GET timeout for %s", url)
        raise RuntimeError("Request to Valorant API timed out. Please try again later.") from exc


async def close_session():
    global _session
    if _session and not _session.closed:
        logger.debug("Closing aiohttp ClientSession")
        await _session.close()
        _session = None
