import discord
from discord import app_commands
from discord.ext import commands
from core.utils import check_cooldown, norm_region, q
from core.http import http_get
from core.store import upsert_link, pop_link, get_link
from core.config import HENRIK_BASE

class LinkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="link", description="Link your Riot ID (consent to fetch stats)")
    @app_commands.describe(name="Riot ID name", tag="Riot ID tag", region="ap/kr/eu/na/…")
    async def link(self, inter: discord.Interaction, name: str, tag: str, region: str = "ap"):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        region = norm_region(region)
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            if acc.get("status") != 200:
                raise RuntimeError("Account not found")
            upsert_link(inter.user.id, name, tag, region)
            await inter.followup.send(f"Linked: **{name}#{tag}** ({region.upper()})", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="unlink", description="Unlink Riot ID")
    async def unlink(self, inter: discord.Interaction):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        info = pop_link(inter.user.id)
        if info:
            await inter.followup.send(f"Unlinked: {info['name']}#{info['tag']}", ephemeral=True)
        else:
            await inter.followup.send("No linked info.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LinkCog(bot))
