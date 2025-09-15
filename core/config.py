import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# env
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN") or ""
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY") or ""

# endpoints
HENRIK_BASE = "https://api.henrikdev.xyz/valorant"
VAL_ASSET   = "https://valorant-api.com/v1"

# paths
ROOT_DIR   = Path(__file__).resolve().parents[1]
DATA_DIR   = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"
TIERS_DIR  = ASSETS_DIR / "tiers"

LINKS_FILE = DATA_DIR / "links.json"

# fs bootstrap
DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)
TIERS_DIR.mkdir(exist_ok=True)
if not LINKS_FILE.exists():
    LINKS_FILE.write_text("{}", encoding="utf-8")
