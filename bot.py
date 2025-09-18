# === bot.py (global slash sync with guild logs, cleaned, keep resync cog) ===
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

from core import config

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] %(levelname)s:%(name)s: %(message)s",
)
logger = logging.getLogger("bot")

# ── Intents & Bot ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
# 슬래시 커맨드만 쓰면 아래 줄은 필요 없음
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


# ── Global slash command sync only ────────────────────────────────────────────
async def _sync_app_commands_global():
    synced = await bot.tree.sync()  # 전역 동기화 (모든 길드)
    logger.info("Slash commands synced globally (count=%d)", len(synced))
    for g in bot.guilds:
        logger.info("  ↳ Synced for guild: %s (%s)", g.name, g.id)


# ── Lifecycle hooks ───────────────────────────────────────────────────────────
@bot.event
async def setup_hook():
    await _load_all_cogs()
    await _sync_app_commands_global()


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "?")
    logger.info("Connected to %d guild(s)", len(bot.guilds))
    for g in bot.guilds:
        logger.info("  ↳ Guild: %s (%s), members=%d", g.name, g.id, g.member_count)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
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

    # 파일시스템 부트스트랩(임포트 시 부작용 없음)
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