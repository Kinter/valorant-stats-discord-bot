from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import get_link, pop_link, upsert_link
from core.utils import (
    check_cooldown,
    clean_text,
    norm_region,
    q,
    is_account_not_found_error,
    format_exception_message,
)


class LinkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    link_name_desc = locale_str("Riot ID name")
    link_name_desc.localize("ko", "라이엇 ID 이름")
    link_tag_desc = locale_str("Riot ID tag")
    link_tag_desc.localize("ko", "라이엇 ID 태그")
    link_region_desc = locale_str("Valorant region (ap/kr/eu/na/...)")
    link_region_desc.localize("ko", "서버 지역 (ap/kr/eu/na/...)")

    @app_commands.command(
        name="link",
        description="Link your Riot ID to the bot.",
        name_localizations={"ko": "계정연결"},
        description_localizations={"ko": "라이엇 ID를 봇과 연결합니다."},
    )
    @app_commands.describe(
        name=link_name_desc,
        tag=link_tag_desc,
        region=link_region_desc,
    )
    async def link(self, inter: discord.Interaction, name: str, tag: str, region: Optional[str] = "ap"):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초", ephemeral=True
            )
            return

        name = clean_text(name)
        tag = clean_text(tag)
        region = norm_region(region or "ap")

        if not name or not tag:
            await inter.response.send_message("라이엇 ID 이름과 태그를 모두 입력해 주세요.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            if acc.get("status") != 200:
                raise RuntimeError("Account not found")
            upsert_link(inter.user.id, name, tag, region)
            await inter.followup.send(f"연결 완료: **{name}#{tag}** ({region.upper()})", ephemeral=True)
        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send("계정을 찾을 수 없습니다. 계정 이름과 태그를 확인해 주세요.", ephemeral=True)
            else:
                err = format_exception_message(e)
                await inter.followup.send(f"연결에 실패했습니다: {err}", ephemeral=True)

    @app_commands.command(
        name="unlink",
        description="Unlink your Riot ID from the bot.",
        name_localizations={"ko": "계정연결해제"},
        description_localizations={"ko": "연결된 라이엇 ID를 해제합니다."},
    )
    async def unlink(self, inter: discord.Interaction):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초", ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        info = pop_link(inter.user.id)
        if info:
            await inter.followup.send(f"연결 해제: {info['name']}#{info['tag']}", ephemeral=True)
        else:
            await inter.followup.send("연결된 계정이 없습니다.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LinkCog(bot))
