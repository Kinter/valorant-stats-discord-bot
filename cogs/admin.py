import discord
from discord import app_commands
from discord.ext import commands

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="명령동기화", description="슬래시 명령을 다시 동기화합니다 (관리자 전용).")
    async def resync(self, inter: discord.Interaction):
        app = await self.bot.application_info()
        if inter.user.id != app.owner.id:
            await inter.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await inter.followup.send(f"{len(synced)}개의 명령을 다시 동기화했습니다.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"동기화 중 오류가 발생했습니다: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
