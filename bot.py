from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

from core import config  # central config/env

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] %(levelname)s:%(name)s: %(message)s",
)
logger = logging.getLogger("bot")

# ── Intents & Bot ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
# If you need to process message content (legacy text commands), uncomment:
# intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

COGS_DIR = Path(__file__).parent / "cogs"


# ── Cog discovery/loading ─────────────────────────────────────────────────────

def _discover_cogs() -> list[str]:
    if not COGS_DIR.exists():
        logger.warning("No cogs directory found at %s", COGS_DIR)
        return []
    return [
        f"cogs.{p.stem}"
        for p in COGS_DIR.glob("*.py")
        if not p.name.startswith("_")
    ]


async def _load_all_cogs():
    modules = _discover_cogs()
    if not modules:
        logger.info("No cogs to load.")
        return
    for module in modules:
        try:
            await bot.load_extension(module)
            logger.info("Loaded cog: %s", module)
        except commands.ExtensionAlreadyLoaded:
            await bot.reload_extension(module)
            logger.info("Reloaded cog: %s", module)
        except Exception:
            logger.exception("Failed to load cog: %s", module)


# ── Slash command sync ────────────────────────────────────────────────────────
async def _sync_app_commands():
    guild_id = config.GUILD_ID
    if guild_id:
        try:
            gid = int(guild_id)
        except ValueError:
            logger.error("GUILD_ID must be an integer. Got: %r", guild_id)
            return
        synced = await bot.tree.sync(guild=discord.Object(id=gid))
        logger.info("Slash commands synced to guild %s (count=%d)", gid, len(synced))
    else:
        synced = await bot.tree.sync()
        logger.info("Slash commands synced globally (count=%d)", len(synced))


# ── Lifecycle hooks ───────────────────────────────────────────────────────────
@bot.event
async def setup_hook():
    await _load_all_cogs()
    await _sync_app_commands()


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "?")
    logger.info("Connected to %d guild(s)", len(bot.guilds))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    # Basic handler for legacy text commands (if you still use any)
    if isinstance(error, commands.CommandNotFound):
        return
    logger.exception("Command error: %s", error)
    try:
        await ctx.reply("⚠️ 문제가 발생했습니다. 잠시 후 다시 시도하세요.")
    except Exception:
        pass


# ── Entrypoint ───────────────────────────────────────────────────────────────
async def main():
    if not config.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN이 비어 있습니다. .env 또는 환경변수를 설정하세요.")
        sys.exit(1)

    # Perform filesystem bootstrap once at startup (no import-time side effects)
    config.bootstrap_fs()

    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down (KeyboardInterrupt)…")
    except Exception:
        logger.exception("Fatal error during bot runtime")
        raise
