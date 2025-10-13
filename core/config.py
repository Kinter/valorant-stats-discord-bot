import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# env
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or ""
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY") or ""
LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").upper()
_guild_id_raw = os.getenv("GUILD_ID")
#_guild_id_raw = os.getenv()
if _guild_id_raw:
    _guild_id_token = _guild_id_raw.split()[0]
    try:
        GUILD_ID = int(_guild_id_token)
    except ValueError:
        GUILD_ID = None
else:
    GUILD_ID = None

# endpoints
HENRIK_BASE = "https://api.henrikdev.xyz/valorant"
VAL_ASSET   = "https://valorant-api.com/v1"

# paths
ROOT_DIR   = Path(__file__).resolve().parents[1]
DATA_DIR   = ROOT_DIR / "data"
ASSETS_DIR = ROOT_DIR / "assets"
TIERS_DIR  = ASSETS_DIR / "tiers"
LOG_FILE   = DATA_DIR / "bot.log"

DB_FILE = DATA_DIR / "bot.sqlite3"

# fs bootstrap
DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)
TIERS_DIR.mkdir(exist_ok=True)
