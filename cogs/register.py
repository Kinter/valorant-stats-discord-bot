from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import get_alias, list_aliases, remove_alias, upsert_alias
from core.utils import check_cooldown, clean_text, norm_region, q, is_account_not_found_error


class RegisterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="register", description="Register a player alias for quick lookup")
    @app_commands.describe(
        alias="Friendly alias to reference later",
        name="Riot ID name",
        tag="Riot ID tag",
        region="Valorant region (ap/kr/eu/na/...)",
    )
    async def register(
        self,
        inter: discord.Interaction,
        alias: str,
        name: str,
        tag: str,
        region: Optional[str] = None,
    ):
        alias = clean_text(alias)
        name = clean_text(name)
        tag = clean_text(tag)
        region = norm_region(region or "ap")
        if not alias:
            await inter.response.send_message("Alias cannot be empty.", ephemeral=True)
            return
        if len(alias) > 32:
            await inter.response.send_message("Alias must be 32 characters or fewer.", ephemeral=True)
            return
        if not name or not tag:
            await inter.response.send_message("Name and tag must not be empty.", ephemeral=True)
            return

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            if acc.get("status") != 200:
                raise RuntimeError("Account not found")
            data = acc.get("data") or {}
            puuid = data.get("puuid")
            if not puuid:
                raise RuntimeError("Puuid missing in HenrikDev response")

            upsert_alias(alias, name, tag, region, puuid)
            await inter.followup.send(f"Registered **{alias}** -> **{name}#{tag}** ({region.upper()})", ephemeral=True)
        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send("계정을 찾을 수 없습니다. 계정 이름과 태그를 확인해 주세요.", ephemeral=True)
            else:
                await inter.followup.send(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="unregister", description="Remove a player alias")
    @app_commands.describe(alias="Alias to remove")
    async def unregister(self, inter: discord.Interaction, alias: str):
        alias = clean_text(alias)
        if not alias:
            await inter.response.send_message("Alias cannot be empty.", ephemeral=True)
            return

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        removed = remove_alias(alias)
        if removed:
            await inter.followup.send(f"Removed alias **{alias}**", ephemeral=True)
        else:
            await inter.followup.send(f"Alias **{alias}** not found.", ephemeral=True)

    @app_commands.command(name="aliases", description="List registered aliases")
    async def aliases(self, inter: discord.Interaction):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        records = list_aliases()
        if not records:
            await inter.response.send_message("No aliases registered.", ephemeral=True)
            return

        lines = [
            f"- **{rec['alias']}** -> {rec['name']}#{rec['tag']} ({rec['region'].upper()})"
            for rec in records
        ]
        await inter.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RegisterCog(bot))
