from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands
from core.utils import alias_display, check_cooldown, clean_text, is_account_not_found_error, q
from core.http import http_get
from core.store import get_alias, get_link, search_aliases
from core.config import HENRIK_BASE

class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_target(self, user_id: int) -> Optional[tuple[str, str, str]]:
        info = get_link(user_id)
        if not info:
            return None
        return info["name"], info["tag"], info.get("region", "ap")

    @app_commands.command(name="vprofile", description="View profile and MMR of linked Riot ID")
    @app_commands.describe(target="Registered alias to inspect (empty = your linked account)")
    async def vprofile(self, inter: discord.Interaction, target: Optional[str] = None):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        alias_input = clean_text(target)
        if alias_input:
            alias_info = get_alias(alias_input)
            if not alias_info:
                await inter.response.send_message(f"Alias `{alias_input}` not found.", ephemeral=True)
                return
            name = alias_info["name"]
            tag = alias_info["tag"]
            region = alias_info.get("region", "ap")
        else:
            resolved = self._resolve_target(inter.user.id)
            if resolved is None:
                await inter.response.send_message("not linking", ephemeral=True)
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

            embed = discord.Embed(
                title=f"{name}#{tag}",
                description=f"Level {level} • {title}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Region", value=region.upper())
            embed.add_field(name="Rank", value=f"{tier} ({rr} RR)")
            if card.get("small"):
                embed.set_thumbnail(url=card["small"])
            await inter.followup.send(embed=embed)

        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send("계정을 찾을 수 없습니다. 계정 이름과 태그를 확인해 주세요.")
            else:
                msg = str(e) or e.__class__.__name__
                await inter.followup.send(f"Error: {msg}")

    def _alias_choices(self, query: Optional[str]) -> List[app_commands.Choice[str]]:
        records = search_aliases(query, limit=25)
        return [
            app_commands.Choice(name=alias_display(rec), value=rec["alias"])
            for rec in records
        ]

    @vprofile.autocomplete("target")
    async def vprofile_target_autocomplete(
        self,
        inter: discord.Interaction,
        current: str,
    ):
        return self._alias_choices(current)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
