from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import get_alias, search_aliases
from core.utils import (
    ALIAS_REGISTRATION_PROMPT,
    alias_display,
    check_cooldown,
    clean_text,
    format_exception_message,
    is_account_not_found_error,
    q,
)


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    vprofile_target_desc = locale_str(
        "Registered alias to inspect", ko="조회할 사람을 선택하여 주세요"
    )

    @app_commands.command(
        name="프로필",
        description="프로필과 MMR을 조회합니다.",
    )
    @app_commands.describe(target=vprofile_target_desc)
    async def vprofile(
        self, inter: discord.Interaction, target: Optional[str] = None
    ) -> None:
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후에 다시 시도해 주세요. 남은 시간: {remain}초", ephemeral=True
            )
            return

        alias_input = clean_text(target)
        if not alias_input:
            await inter.response.send_message(
                ALIAS_REGISTRATION_PROMPT,
                ephemeral=True,
            )
            return

        alias_info = get_alias(alias_input)
        if not alias_info:
            await inter.response.send_message(
                f"`{alias_input}` 별명을 찾을 수 없습니다.", ephemeral=True
            )
            return

        name = alias_info["name"]
        tag = alias_info["tag"]
        region = alias_info.get("region", "ap")

        await inter.response.defer()
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            data = acc.get("data", {}) or {}
            card = data.get("card", {}) or {}
            level = data.get("account_level", 0)
            title = data.get("title") or ""

            mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
            cur = (mmr.get("data") or {}).get("current_data") or {}
            tier = cur.get("currenttierpatched") or "Unrated"
            rr = cur.get("ranking_in_tier", 0)

            title_text = f" | {title}" if title else ""
            embed = discord.Embed(
                title=f"{name}#{tag}",
                description=f"계정 레벨 {level}{title_text}",
                color=discord.Color.blue(),
            )
            embed.add_field(name="지역", value=region.upper())
            embed.add_field(name="랭크", value=f"{tier} ({rr} RR)")
            if card.get("small"):
                embed.set_thumbnail(url=card["small"])

            await inter.followup.send(embed=embed)
        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send(
                    "계정을 찾을 수 없습니다. Riot ID 이름과 태그를 확인해 주세요.",
                    ephemeral=True,
                )
            else:
                msg = format_exception_message(e)
                await inter.followup.send(
                    f"오류가 발생했습니다: {msg}", ephemeral=True
                )

    def _alias_choices(
        self, query: Optional[str]
    ) -> List[app_commands.Choice[str]]:
        records = search_aliases(query, limit=25)
        return [
            app_commands.Choice(name=alias_display(rec), value=rec["alias"])
            for rec in records
        ]

    @vprofile.autocomplete("target")
    async def vprofile_target_autocomplete(
        self, inter: discord.Interaction, current: str
    ):
        return self._alias_choices(current)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
