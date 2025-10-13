import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.utils import check_cooldown, clean_text
from core.http import http_get
from core.config import VAL_ASSET


class AgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    vagent_name_desc = locale_str("Agent name (e.g., Jett, Sage, Sova)")
    vagent_name_desc.localize("ko", "요원 이름 (예: 제트, 세이지, 소바)")

    @app_commands.command(
        name="vagent",
        description="Get agent info (image and description).",
        name_localizations={"ko": "요원정보"},
        description_localizations={"ko": "요원 정보를 확인합니다 (이미지/설명)."},
    )
    @app_commands.describe(name=vagent_name_desc)
    async def vagent(self, inter: discord.Interaction, name: str):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초", ephemeral=True)
            return

        name = clean_text(name)
        if not name:
            await inter.response.send_message("요원 이름을 입력해 주세요.", ephemeral=True)
            return

        await inter.response.defer()
        try:
            agents = await http_get(f"{VAL_ASSET}/agents", params={"isPlayableCharacter": "true"})
            arr = agents.get("data") or []
            found = next(
                (a for a in arr if clean_text(a.get("displayName", "")).lower() == name.lower()),
                None,
            )
            if not found:
                await inter.followup.send("해당 요원을 찾을 수 없습니다.")
                return

            embed = discord.Embed(
                title=found.get("displayName", "Agent"),
                description=found.get("description", ""),
                color=discord.Color.green(),
            )
            icon = found.get("displayIconSmall") or found.get("displayIcon")
            if icon:
                embed.set_thumbnail(url=icon)
            role = (found.get("role") or {}).get("displayName", "")
            if role:
                embed.add_field(name="역할", value=role)

            await inter.followup.send(embed=embed)

        except Exception as e:
            await inter.followup.send(f"오류가 발생했습니다: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AgentCog(bot))
