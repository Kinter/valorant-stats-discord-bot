import discord
from discord import app_commands
from discord.ext import commands

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="resync", description="Resync slash commands (owner only)")
    async def resync(self, inter: discord.Interaction):
        app = await self.bot.application_info()
        if inter.user.id != app.owner.id:
            await inter.response.send_message("Permission denied.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await inter.followup.send(f"Resynced {len(synced)} commands.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Resync error: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
