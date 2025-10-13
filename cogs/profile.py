from typing import Optional, List

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import get_alias, get_link, search_aliases
from core.utils import (
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

    def _resolve_target(self, user_id: int) -> Optional[tuple[str, str, str]]:
        info = get_link(user_id)
        if not info:
            return None
        return info["name"], info["tag"], info.get("region", "ap")

    vprofile_target_desc = locale_str("Registered alias to inspect (empty = your linked account)")
    vprofile_target_desc.localize("ko", "조회할 등록 별칭 (비우면 내 계정)")

    @app_commands.command(
        name="vprofile",
        description="View the profile and MMR of your linked Riot ID.",
        name_localizations={"ko": "프로필"},
        description_localizations={"ko": "연결된 라이엇 ID의 프로필과 MMR을 확인합니다."},
    )
    @app_commands.describe(target=vprofile_target_desc)
    async def vprofile(self, inter: discord.Interaction, target: Optional[str] = None):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초", ephemeral=True)
            return

        alias_input = clean_text(target)
        if alias_input:
            alias_info = get_alias(alias_input)
            if not alias_info:
                await inter.response.send_message(f"`{alias_input}` 별칭을 찾을 수 없습니다.", ephemeral=True)
                return
            name = alias_info["name"]
            tag = alias_info["tag"]
            region = alias_info.get("region", "ap")
        else:
            resolved = self._resolve_target(inter.user.id)
            if resolved is None:
                await inter.response.send_message("연결된 계정이 없습니다.", ephemeral=True)
                return
            name, tag, region = resolved

        await inter.response.defer()
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            data = acc.get("data", {})
            card = data.get("card", {})
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
                await inter.followup.send("계정을 찾을 수 없습니다. 계정 이름과 태그를 확인해 주세요.")
            else:
                msg = format_exception_message(e)
                await inter.followup.send(f"오류가 발생했습니다: {msg}")

    def _alias_choices(self, query: Optional[str]) -> List[app_commands.Choice[str]]:
        records = search_aliases(query, limit=25)
        return [app_commands.Choice(name=alias_display(rec), value=rec["alias"]) for rec in records]

    @vprofile.autocomplete("target")
    async def vprofile_target_autocomplete(self, inter: discord.Interaction, current: str):
        return self._alias_choices(current)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
