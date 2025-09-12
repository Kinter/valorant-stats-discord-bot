import asyncio
import logging
import discord
from discord.ext import commands
from core.config import DISCORD_TOKEN
from core.http import close_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s"
)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

COGS = [
    "cogs.link",
    "cogs.summary",
    "cogs.profile",
    "cogs.matches",
    "cogs.agent",
    "cogs.admin",
]

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        logging.info(f"[SYNC] Global slash synced: {len(synced)}")
    except Exception as e:
        logging.exception("[SYNC ERROR] %s", e)

    logging.info(f"[GUILDS] {len(bot.guilds)} connected")
    for g in bot.guilds:
        m = getattr(g, "member_count", "?")
        logging.info(f" - {g.name} (ID: {g.id}) members≈{m}")
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

async def main():
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing in .env")
    # load cogs
    for ext in COGS:
        try:
            await bot.load_extension(ext)
            logging.info(f"[COG] loaded: {ext}")
        except Exception as e:
            logging.exception(f"[COG ERROR] {ext}: {e}")

    try:
        await bot.start(DISCORD_TOKEN)
    finally:
        await close_session()

if __name__ == "__main__":
    asyncio.run(main())
