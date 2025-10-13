import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from core.config import DISCORD_TOKEN, LOG_LEVEL, GUILD_ID, LOG_FILE
from core.http import close_session


def _resolve_log_level(name: str) -> int:
    numeric = getattr(logging, name, None)
    if isinstance(numeric, int):
        return numeric
    try:
        return int(name)
    except (TypeError, ValueError):
        return logging.INFO


_log_level = _resolve_log_level(LOG_LEVEL)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)

discord_logger = logging.getLogger("discord")
discord_http_logger = logging.getLogger("discord.http")
discord_logger.setLevel(max(_log_level, logging.INFO))
discord_http_logger.setLevel(max(_log_level, logging.INFO))
logging.getLogger(__name__).info("Logging initialised at level %s", logging.getLevelName(_log_level))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def _describe_context(user: discord.abc.User, guild: Optional[discord.Guild]) -> str:
    user_repr = f"{user} (ID: {user.id})"
    if guild is None:
        return f"{user_repr} in DM"
    return f"{user_repr} in {guild.name} (ID: {guild.id})"

COGS = [
    "cogs.link",
    "cogs.register",
    "cogs.summary",
    "cogs.profile",
    "cogs.matches",
    "cogs.agent",
    "cogs.admin",
]


@bot.listen("on_app_command_completion")
async def log_app_command_completion(interaction: discord.Interaction, command: app_commands.Command):
    logging.info("[CMD] /%s by %s", command.qualified_name, _describe_context(interaction.user, interaction.guild))


@bot.listen("on_app_command_error")
async def log_app_command_error(
    interaction: discord.Interaction, command: app_commands.Command, error: app_commands.AppCommandError
):
    logging.error(
        "[CMD ERROR] /%s by %s",
        command.qualified_name,
        _describe_context(interaction.user, interaction.guild),
        exc_info=(type(error), error, error.__traceback__),
    )


@bot.event
async def on_command_completion(ctx: commands.Context):
    logging.info("[CMD] !%s by %s", ctx.command.qualified_name, _describe_context(ctx.author, ctx.guild))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    command_name = ctx.command.qualified_name if ctx.command else "?"
    logging.error(
        "[CMD ERROR] !%s by %s",
        command_name,
        _describe_context(ctx.author, ctx.guild),
        exc_info=(type(error), error, error.__traceback__),
    )


@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
            logging.info(f"[SYNC] Guild slash synced for testing ({GUILD_ID}): {len(synced)}")
        else:
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
        try:
            if not bot.is_closed():
                await bot.close()
        finally:
            await close_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt. Shutting down.")
