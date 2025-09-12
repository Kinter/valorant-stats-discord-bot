import discord
from discord import app_commands
from discord.ext import commands
from core.utils import check_cooldown
from core.http import http_get
from core.config import VAL_ASSET

class AgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="vagent", description="Get agent info (image & description)")
    @app_commands.describe(name="Agent name, e.g., Jett, Sage, Sova")
    async def vagent(self, inter: discord.Interaction, name: str):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer()
        try:
            agents = await http_get(f"{VAL_ASSET}/agents", params={"isPlayableCharacter": "true"})
            arr = agents.get("data") or []
            found = next((a for a in arr if a.get("displayName", "").lower() == name.lower()), None)
            if not found:
                await inter.followup.send("Agent not found.")
                return

            embed = discord.Embed(
                title=found.get("displayName", "Agent"),
                description=found.get("description", ""),
                color=discord.Color.green()
            )
            icon = found.get("displayIconSmall") or found.get("displayIcon")
            if icon: embed.set_thumbnail(url=icon)
            role = (found.get("role") or {}).get("displayName", "")
            if role: embed.add_field(name="Role", value=role)

            await inter.followup.send(embed=embed)

        except Exception as e:
            await inter.followup.send(f"Error: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AgentCog(bot))
