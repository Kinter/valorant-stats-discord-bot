import discord
from discord import app_commands
from discord.ext import commands
from core.utils import check_cooldown, q
from core.http import http_get
from core.store import get_link
from core.config import HENRIK_BASE

class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_target(self, user_id: int):
        info = get_link(user_id)
        if not info:
            raise RuntimeError("No linked Riot ID. Use /link first.")
        return info["name"], info["tag"], info.get("region", "ap")

    @app_commands.command(name="vprofile", description="View profile and MMR of linked Riot ID")
    async def vprofile(self, inter: discord.Interaction):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer()
        try:
            name, tag, region = self._resolve_target(inter.user.id)
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
            await inter.followup.send(f"Error: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
