from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env once (safe if file is absent)
load_dotenv()

# ── Environment values (strings by default) ───────────────────────────────────
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN") or ""
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY") or ""
GUILD_ID       = os.getenv("GUILD_ID") or ""   # optional; used for fast guild-only slash sync
LOG_LEVEL      = (os.getenv("LOG_LEVEL") or "INFO").upper()

# ── External endpoints ────────────────────────────────────────────────────────
HENRIK_BASE = "https://api.henrikdev.xyz/valorant"
VAL_ASSET   = "https://valorant-api.com/v1"

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).resolve().parents[1]
DATA_DIR   = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"
TIERS_DIR  = ASSETS_DIR / "tiers"

LINKS_FILE = DATA_DIR / "links.json"

# ── Bootstrap helper (no side-effects at import time) ─────────────────────────

def bootstrap_fs() -> None:
    """Create required directories/files once at startup.
    This avoids side-effects during module import.
    """
    DATA_DIR.mkdir(exist_ok=True)
    ASSETS_DIR.mkdir(exist_ok=True)
    TIERS_DIR.mkdir(exist_ok=True)
    if not LINKS_FILE.exists():
        LINKS_FILE.write_text("{}", encoding="utf-8")
